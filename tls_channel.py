




from collections import deque
import math
import re
import select
import socket
import ssl
import struct
import sys
import threading
import time



PROGRESS_PROFILE = 'bounded-progress-v1'
WRITE_CHUNK_BYTES = 16 * 1024
_PROGRESS_LIMITS = dict(write_timeout=24., write_idle_timeout=12.,
                        frame_timeout=30., read_idle_timeout=12., queue_timeout=30.)
_TIMEOUT_KINDS = frozenset({'none', 'handshake', 'initial', 'read_frame', 'write_frame',
                          'write_idle', 'read_idle', 'queue', 'finish'})
_BYTE_COUNTS = frozenset({'write_frame_bytes', 'write_accepted_bytes', 'read_frame_bytes',
                         'read_received_bytes', 'outgoing_frames', 'outgoing_bytes',
                         'incoming_frames', 'incoming_bytes', 'write_chunk_bytes',
                         'write_calls', 'read_calls', 'write_want_read_count', 'write_want_write_count',
                         'read_want_read_count', 'read_want_write_count', 'select_readable_count',
                         'select_writable_count', 'tcp_retransmit_packets', 'tcp_retransmit_bytes',
                         'tcp_write_start_retransmit_packets', 'tcp_write_retransmit_packets_delta',
                         'tcp_send_buffer_bytes', 'tcp_send_window_bytes', 'tcp_unacked_packets',
                         'tcp_send_cwnd_bytes', 'tcp_send_cwnd_packets'})
_MILLISECONDS = frozenset({'write_elapsed_ms', 'queue_elapsed_ms', 'read_elapsed_ms',
                           'write_limit_ms', 'queue_limit_ms', 'frame_limit_ms',
                           'write_idle_ms', 'read_idle_ms', 'write_idle_limit_ms', 'read_idle_limit_ms',
                           'read_paused_ms', 'read_pause_max_ms', 'owner_loop_gap_max_ms', 'tcp_rtt_ms'})


def safe_transport_details(value):
    
    if not isinstance(value, dict):
        return {}
    result = {}
    kind = value.get('timeout_kind')
    if isinstance(kind, str) and kind in _TIMEOUT_KINDS:
        result['timeout_kind'] = kind
    for key in _BYTE_COUNTS:
        number = value.get(key)
        if type(number) is int and 0 <= number <= 2**53-1:
            result[key] = number
    for key in _MILLISECONDS:
        number = value.get(key)
        if type(number) in (int, float) and 0 <= number <= 86400000 and math.isfinite(number):
            result[key] = round(number, 3)
    return result


_STAGE_TRACE_EVENTS = frozenset({
    'tls_send_queued', 'tls_send_started', 'tls_ssl_accepted', 'tls_send_complete',
    'tls_recv_frame_complete', 'tls_recv_dequeued',
    'app_chunk_read', 'app_frame_encoded', 'app_send_begin', 'app_send_done',
    'app_frame_received', 'app_chunk_decoded', 'app_queue_begin', 'app_queue_done',
    'app_write_begin', 'app_write_done'})
_STAGE_TRACE_COUNTS = frozenset({
    'frame_seq', 'chunk_seq', 'stream_seq', 'data_bytes', 'frame_bytes',
    'chunk_bytes', 'accepted_bytes', 'outgoing_frames', 'outgoing_bytes',
    'incoming_frames', 'incoming_bytes', 'tcp_maxseg_bytes', 'tcp_info_maxseg_bytes'}) | frozenset(
        name for name in _BYTE_COUNTS if name.startswith('tcp_'))
_STAGE_TRACE_TIMES = frozenset({'elapsed_ms', 'queue_elapsed_ms', 'call_elapsed_ms', 'tcp_rtt_ms'})
_STAGE_TRACE_TEXT = {
    'direction': frozenset({'browser_to_core', 'core_to_browser'}),
    'status': frozenset({'ok', 'begin', 'complete', 'queued', 'accepted', 'stopped', 'error'})}
_STAGE_META_FIELDS = frozenset({'stream_token', 'chunk_seq', 'direction'})


def _stage_details(value):
    
    if type(value) is not dict:
        return None
    result = {}
    for key, number in value.items():
        if key in _STAGE_TRACE_COUNTS:
            if type(number) is not int or not 0 <= number <= 2**53-1:
                return None
            if key in ('frame_seq', 'chunk_seq', 'stream_seq') and number == 0:
                return None
            result[key] = number
        elif key in _STAGE_TRACE_TIMES:
            if type(number) not in (int, float) or not 0 <= number <= 86400000 or not math.isfinite(number):
                return None
            result[key] = round(number, 3)
        elif key in _STAGE_TRACE_TEXT:
            if type(number) is not str or number not in _STAGE_TRACE_TEXT[key]:
                return None
            result[key] = number
        elif key == 'stream_token':
            if type(number) is not str or re.fullmatch(r'[0-9a-f]{64}', number) is None:
                return None
            result[key] = number
        else:
            return None
    return result


class TransportStageTrace:
    






    def __init__(self, capacity=4096):
        if type(capacity) is not int or not 1 <= capacity <= 8192:
            raise ValueError('invalid stage trace capacity')
        self.capacity = capacity
        self._records = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._sequence = self._evicted = self._dropped = self._invalid = 0

    def record(self, stage, **metadata):
        details = _stage_details(metadata)
        if type(stage) is not str or stage not in _STAGE_TRACE_EVENTS or details is None:
            self._invalid += 1
            return False
        if not self._lock.acquire(blocking=False):
            self._dropped += 1
            return False
        try:
            self._sequence += 1
            if len(self._records) == self.capacity:
                self._evicted += 1
            self._records.append(dict(stage=stage, event_seq=self._sequence,
                monotonic_ns=time.monotonic_ns(), at_unix_us=time.time_ns()//1000, **details))
        finally:
            self._lock.release()
        return True

    def snapshot(self):
        
        with self._lock:
            return dict(schema='eh-transport-stage/1', capacity=self.capacity,
                total_events=self._sequence, evicted_events=self._evicted,
                dropped_events=self._dropped, invalid_events=self._invalid,
                records=[dict(record) for record in self._records])


class ChannelError(Exception):
    def __init__(self, code, operation='none', cause=None, *, timeout_kind='none'):
        super().__init__(code)
        self.code, self.operation, self.cause = code, operation, cause
        self.timeout_kind = timeout_kind
        self.details = {}
        self.at_unix, self.monotonic_ns = time.time(), time.monotonic_ns()


class TLSChannel:
    def __init__(self, raw, context, *, server_side=False, server_hostname=None,
                 max_frame=2*1024*1024, initial_frame=4096, max_frames=64,
                 max_bytes=4*1024*1024, handshake_timeout=5., initial_timeout=5.,
                 frame_timeout=10., write_timeout=10., queue_timeout=10.,
                 write_idle_timeout=None, read_idle_timeout=None,
                 stop_event=None, rejection_frame=None, stage_trace=None):
        if stage_trace is not None and type(stage_trace) is not TransportStageTrace:
            raise ValueError('invalid stage trace ring')
        self._stage_trace = stage_trace
        self._trace_outgoing, self._trace_incoming = deque(), deque()
        self._trace_send_seq = self._trace_recv_seq = 0
        self._trace_current = None
        self._raw, self._context = raw, context
        self._server_side, self._hostname = server_side, server_hostname
        self.max_frame, self.initial_frame = max_frame, initial_frame
        self.max_frames, self.max_bytes = max_frames, max_bytes
        self.handshake_timeout, self.initial_timeout = handshake_timeout, initial_timeout
        self.frame_timeout, self.write_timeout, self.queue_timeout = frame_timeout, write_timeout, queue_timeout
        self.write_idle_timeout, self.read_idle_timeout = write_idle_timeout, read_idle_timeout
        self._stop = stop_event if stop_event is not None else threading.Event()
        self.done, self.ready, self._active = threading.Event(), threading.Event(), threading.Event()
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)

        self._wake_lock = threading.Lock()
        self._wake_reader = self._wake_writer = None
        self._wake_pending = False
        self._incoming, self._outgoing = deque(), deque()
        self._in_bytes = self._in_count = self._out_bytes = self._out_count = 0
        self.error = None
        self.thread = None
        self.owner_ident = None
        self._operation = 'none'
        self._socket = None
        self._initial_received = False
        self._header, self._body = bytearray(), bytearray()
        self._length = None
        self._reserved = False
        self._frame_started = None
        self._read_want = 'read'
        self._current = None
        self._current_receipt = None
        self._offset = 0
        self._write_want = 'write'
        self._write_started = None
        self._queued_at = None
        self._write_progress_at = self._read_progress_at = None
        self._write_end = None
        self._write_tcp_start = {}
        self._activation_pending = False
        self._requested_profile = None
        self._profile = None
        self._read_paused_at = None
        self._read_pause_max = 0.
        self._owner_loop_at = None
        self._owner_loop_gap_max = 0.
        self._counts = dict.fromkeys(('write_calls', 'read_calls', 'write_want_read_count',
            'write_want_write_count', 'read_want_read_count', 'read_want_write_count',
            'select_readable_count', 'select_writable_count'), 0)
        self._handshaken_at = None
        self._finish = False
        self._finish_started = None
        self.shutdown_status = "not_started"
        self._rejection_frame = rejection_frame
        if not (0 < initial_frame <= max_frame and max_frame + 4 <= max_bytes and max_frames > 0):
            raise ValueError('invalid TLS channel limits')

    def set_stage_trace(self, trace):
        
        if trace is not None and type(trace) is not TransportStageTrace:
            raise ValueError('invalid stage trace ring')
        with self._lock:
            if (self.thread is not None or self._out_count or self._in_count
                    or self._current is not None or self._header or self._body
                    or self._initial_received or any(self._counts.values())):
                raise ValueError('stage trace requires unused channel')
            self._stage_trace = trace

    def trace_stage(self, stage, **metadata):
        trace = self._stage_trace
        return False if trace is None else trace.record(stage, **metadata)

    def trace_snapshot(self):
        trace = self._stage_trace
        return None if trace is None else trace.snapshot()

    def _trace_tcp_details(self, baseline=None):
        
        if self._stage_trace is None:
            return {}
        details = self._tcp_details() if baseline is None else dict(baseline)
        try:
            if hasattr(socket, 'TCP_MAXSEG'):
                value = self._socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG)
                if type(value) is int and 0 < value <= 2**31-1:
                    details['tcp_maxseg_bytes'] = value
        except (OSError, ValueError, AttributeError, TypeError):
            pass
        if sys.platform == 'darwin':
            try:

                raw = self._socket.getsockopt(socket.IPPROTO_TCP, 0x106, 112)
                if type(raw) is bytes and len(raw) >= 112:
                    details['tcp_info_maxseg_bytes'] = struct.unpack_from('=I', raw, 16)[0]
            except (OSError, ValueError, AttributeError, TypeError, struct.error):
                pass
        before = self._write_tcp_start.get('tcp_retransmit_packets')
        after = details.get('tcp_retransmit_packets')
        if self._current is not None and type(before) is int and type(after) is int and after >= before:
            details['tcp_write_start_retransmit_packets'] = before
            details['tcp_write_retransmit_packets_delta'] = after-before
        return details

    def start(self):
        if self.thread is not None:
            raise ChannelError('single_use')
        self.thread = threading.Thread(target=self._run, name='eh-tls-io', daemon=True)
        try:
            with self._wake_lock:
                self._wake_reader, self._wake_writer = socket.socketpair()
                self._wake_reader.setblocking(False)
                self._wake_writer.setblocking(False)
            self.thread.start()
        except (OSError, RuntimeError) as exc:


            self._record(ChannelError('worker_start', 'none', exc))
            self._close_wakeup()
            self._raw.close()
            with self._changed:
                self.done.set()
                self._changed.notify_all()
            raise self.error from None
        return self

    def _notify_owner(self):


        with self._wake_lock:
            if self._wake_writer is None or self._wake_pending:
                return
            try:
                self._wake_pending = self._wake_writer.send(b'\0') == 1
            except BlockingIOError:
                self._wake_pending = True
            except OSError:


                pass

    def _drain_wakeup(self):
        with self._wake_lock:
            if self._wake_reader is None:
                return
            try:
                data = self._wake_reader.recv(4096)
                if not data:
                    raise ChannelError('io_error', 'select', EOFError())
            except BlockingIOError:
                pass
            except InterruptedError:
                return
            self._wake_pending = False

    def _close_wakeup(self):
        with self._wake_lock:
            ends = (self._wake_reader, self._wake_writer)
            self._wake_reader = self._wake_writer = None
            self._wake_pending = False
            for end in ends:
                if end is not None:
                    try:
                        end.close()
                    except OSError:
                        pass

    def _select(self, read, write, timeout, *, buffered=False):

        reader = self._wake_reader
        reads = ([reader] if reader is not None else []) + ([self._socket] if read else [])
        r, w, _ = select.select(reads, [self._socket] if write else [], [],
                                0 if buffered else timeout)
        if reader is not None and reader in r:
            self._drain_wakeup()
        self._counts['select_readable_count'] += int(self._socket in r)
        self._counts['select_writable_count'] += int(self._socket in w)


        return self._socket in r or buffered, self._socket in w

    def activate(self, *, profile=None):
        




        if profile not in (None, PROGRESS_PROFILE):
            raise ValueError('unsupported transport profile')
        with self._lock:
            if self._active.is_set():
                if profile != self._profile:
                    raise ValueError('transport profile already active')
                return
            if self._activation_pending and profile != self._requested_profile:
                raise ValueError('transport profile already requested')
            self._activation_pending, self._requested_profile = True, profile
        self._notify_owner()

    def _apply_activation(self):
        with self._lock:
            if not self._activation_pending:
                return
            if self._requested_profile == PROGRESS_PROFILE:
                for name, value in _PROGRESS_LIMITS.items():
                    setattr(self, name, value)
            self._profile = self._requested_profile
            self._activation_pending = False
            self._active.set()

    def _tcp_details(self):
        
        try:
            if sys.platform == 'darwin':

                raw = self._socket.getsockopt(socket.IPPROTO_TCP, 0x106, 112)
                if len(raw) >= 112:
                    return {'tcp_send_cwnd_bytes': struct.unpack_from('=I', raw, 24)[0],
                            'tcp_send_window_bytes': struct.unpack_from('=I', raw, 28)[0],
                            'tcp_send_buffer_bytes': struct.unpack_from('=I', raw, 32)[0],
                            'tcp_rtt_ms': struct.unpack_from('=I', raw, 44)[0],
                            'tcp_retransmit_bytes': struct.unpack_from('=Q', raw, 72)[0],
                            'tcp_retransmit_packets': struct.unpack_from('=Q', raw, 104)[0]}
            elif sys.platform.startswith('linux') and hasattr(socket, 'TCP_INFO'):

                raw = self._socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 104)
                if len(raw) >= 104:
                    return {'tcp_unacked_packets': struct.unpack_from('=I', raw, 24)[0],
                            'tcp_rtt_ms': struct.unpack_from('=I', raw, 68)[0] / 1000.,
                            'tcp_send_cwnd_packets': struct.unpack_from('=I', raw, 80)[0],
                            'tcp_retransmit_packets': struct.unpack_from('=I', raw, 100)[0]}
        except (OSError, ValueError, AttributeError, struct.error):
            pass
        return {}

    def finish(self):
        
        with self._lock:
            self._finish_started = time.monotonic()
            self._finish = True
        self._notify_owner()

    def request_stop(self):
        with self._changed:
            self._stop.set()
            self._changed.notify_all()
        self._notify_owner()

    def join(self, timeout=2.):
        if self.thread is not None and self.thread.ident is not None:
            if self.thread is threading.current_thread():
                return False
            self.thread.join(timeout=timeout)
        return self.done.is_set()

    def send(self, frame, *, wait=False, stage_meta=None):
        




        if wait and threading.get_ident() == self.owner_ident:
            raise ChannelError('owner_cannot_wait', 'queue')
        receipt = threading.Event() if wait else None
        if not isinstance(frame, bytes) or not 4 < len(frame) <= self.max_frame + 4 or struct.unpack('!I', frame[:4])[0] != len(frame)-4:
            raise ChannelError('frame_length', 'queue')
        with self._lock:
            if self.error is not None or self._stop.is_set() or self.done.is_set() or self._finish:
                raise self.error or ChannelError('stopped')
            if self._out_count >= self.max_frames or self._out_bytes + len(frame) > self.max_bytes:
                raise ChannelError('backpressure', 'queue')
            self._outgoing.append((frame, time.monotonic(), receipt))

            self._out_count += 1
            self._out_bytes += len(frame)
            if self._stage_trace is not None:
                self._trace_send_seq += 1
                details = _stage_details(stage_meta) if type(stage_meta) is dict and set(stage_meta) <= _STAGE_META_FIELDS else None
                context = dict(details or {}, frame_seq=self._trace_send_seq)
                self._trace_outgoing.append(context)
                self.trace_stage('tls_send_queued', **context, frame_bytes=len(frame),
                    outgoing_frames=self._out_count, outgoing_bytes=self._out_bytes)
        self._notify_owner()
        if receipt is not None:
            with self._changed:
                while not receipt.is_set():
                    if self.error is not None:
                        raise self.error
                    if self._stop.is_set() or self.done.is_set():
                        raise ChannelError('stopped')
                    self._changed.wait()

    def receive(self, *, stage_meta=None):
        with self._changed:
            while True:
                if self.error is not None:
                    raise self.error
                if self._stop.is_set():
                    raise ChannelError('stopped')
                if self._incoming:
                    value = self._incoming.popleft()
                    self._in_count -= 1
                    self._in_bytes -= len(value) + 4
                    if self._stage_trace is not None:
                        sequence = self._trace_incoming.popleft()
                        if type(stage_meta) is dict and not stage_meta:
                            stage_meta['frame_seq'] = sequence
                        self.trace_stage('tls_recv_dequeued', frame_seq=sequence,
                            frame_bytes=len(value)+4, incoming_frames=self._in_count,
                            incoming_bytes=self._in_bytes)
                    break
                if self.done.is_set():
                    raise ChannelError('eof', 'recv_header')
                self._changed.wait()

        self._notify_owner()
        return value

    def _record(self, error):
        with self._changed:
            if self.error is None and not self._stop.is_set():


                now = time.monotonic()
                queued = self._queued_at
                if queued is None and self._outgoing:
                    queued = self._outgoing[0][1]
                elapsed = lambda start: 0. if start is None else max(0., (now-start)*1000)
                tcp = self._tcp_details()
                before = self._write_tcp_start.get('tcp_retransmit_packets')
                after = tcp.get('tcp_retransmit_packets')
                if self._current is not None and type(before) is int and type(after) is int and after >= before:
                    tcp['tcp_write_start_retransmit_packets'] = before
                    tcp['tcp_write_retransmit_packets_delta'] = after-before
                error.details = safe_transport_details({
                    **self._counts, **tcp,
                    'timeout_kind': error.timeout_kind,
                    'write_frame_bytes': len(self._current) if self._current is not None else 0,

                    'write_accepted_bytes': self._offset if self._current is not None else 0,
                    'read_frame_bytes': self._length or 0,
                    'read_received_bytes': len(self._body),
                    'outgoing_frames': self._out_count, 'outgoing_bytes': self._out_bytes,
                    'incoming_frames': self._in_count, 'incoming_bytes': self._in_bytes,
                    'write_chunk_bytes': WRITE_CHUNK_BYTES,
                    'write_idle_ms': elapsed(self._write_progress_at),
                    'read_idle_ms': elapsed(self._read_progress_at) if self._frame_started is not None else 0.,
                    'write_idle_limit_ms': (self.write_idle_timeout or 0.) * 1000,
                    'read_idle_limit_ms': (self.read_idle_timeout or 0.) * 1000,
                    'read_paused_ms': elapsed(self._read_paused_at),
                    'read_pause_max_ms': max(self._read_pause_max*1000, elapsed(self._read_paused_at)),
                    'owner_loop_gap_max_ms': self._owner_loop_gap_max * 1000,
                    'write_elapsed_ms': elapsed(self._write_started),
                    'queue_elapsed_ms': elapsed(queued), 'read_elapsed_ms': elapsed(self._frame_started),
                    'write_limit_ms': self.write_timeout*1000,
                    'queue_limit_ms': self.queue_timeout*1000, 'frame_limit_ms': self.frame_timeout*1000})
                self.error = error
            self._stop.set()
            self._changed.notify_all()

    def _wait(self, want, deadline):
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ChannelError('handshake_timeout', 'tls_handshake', TimeoutError(), timeout_kind='handshake')
            self._operation = 'select'
            try:
                r, w = self._select(want == 'read', want == 'write', min(.05, remaining))
            except InterruptedError:
                continue
            if r or w:
                return
        raise ChannelError('stopped')

    def _handshake(self):
        deadline = time.monotonic() + self.handshake_timeout
        while not self._stop.is_set():
            self._operation = 'tls_handshake'
            try:
                self._socket.do_handshake()
                self._handshaken_at = time.monotonic()
                self.ready.set()
                return
            except ssl.SSLWantReadError:
                self._wait('read', deadline)
            except ssl.SSLWantWriteError:
                self._wait('write', deadline)
            except (BlockingIOError, InterruptedError):
                self._wait('read', deadline)
        raise ChannelError('stopped')

    def _can_read(self):
        if self._finish or (self._initial_received and not self._active.is_set()):
            return False
        with self._lock:
            if not self._header:
                return self._in_count < self.max_frames and self._in_bytes + 4 <= self.max_bytes
            if self._length is not None and not self._reserved:
                if self._in_count >= self.max_frames or self._in_bytes + self._length + 4 > self.max_bytes:
                    return False
                self._in_count += 1
                self._in_bytes += self._length + 4
                self._reserved = True
        return True

    def _read(self):
        header = self._length is None
        self._operation = 'recv_header' if header else 'recv_body'
        size = 4-len(self._header) if header else min(65536, self._length-len(self._body))
        try:
            self._counts['read_calls'] += 1
            chunk = self._socket.recv(size)
        except ssl.SSLWantReadError:
            self._counts['read_want_read_count'] += 1
            self._read_want = 'read'; return
        except ssl.SSLWantWriteError:
            self._counts['read_want_write_count'] += 1
            self._read_want = 'write'; return
        except (BlockingIOError, InterruptedError):
            self._read_want = 'read'; return
        if not chunk:


            raise ChannelError('peer_closed' if not self._header else 'truncated_frame', self._operation, EOFError())
        self._read_want = 'read'
        self._read_progress_at = time.monotonic()
        if self._frame_started is None:
            self._frame_started = time.monotonic()
        if header:
            self._header.extend(chunk)
            if len(self._header) == 4:
                self._length = struct.unpack('!I', self._header)[0]
                limit = self.max_frame if self._active.is_set() else self.initial_frame
                if not 0 < self._length <= limit:
                    raise ChannelError('frame_length', 'recv_header')
        else:
            self._body.extend(chunk)
            if len(self._body) == self._length:
                with self._changed:
                    self._incoming.append(bytes(self._body))
                    if self._stage_trace is not None:
                        self._trace_recv_seq += 1
                        self._trace_incoming.append(self._trace_recv_seq)
                        self.trace_stage('tls_recv_frame_complete', frame_seq=self._trace_recv_seq,
                            frame_bytes=self._length+4, data_bytes=self._length,
                            elapsed_ms=max(0., (time.monotonic()-self._frame_started)*1000),
                            **self._trace_tcp_details())
                    self._changed.notify_all()
                self._initial_received = True
                self._header, self._body = bytearray(), bytearray()
                self._length, self._frame_started = None, None
                self._reserved = False

    def _take_output(self):
        if self._current is None:
            with self._lock:
                if self._outgoing:
                    self._current, self._queued_at, self._current_receipt = self._outgoing.popleft()
                    self._offset, self._write_started = 0, time.monotonic()
                    self._write_progress_at = self._write_started
                    self._write_end = None
                    self._write_tcp_start = self._tcp_details()
                    self._write_want = 'write'
                    if self._stage_trace is not None:
                        self._trace_current = self._trace_outgoing.popleft()
                        self.trace_stage('tls_send_started', **self._trace_current,
                            frame_bytes=len(self._current),
                            queue_elapsed_ms=max(0., (self._write_started-self._queued_at)*1000),
                            **self._trace_tcp_details(self._write_tcp_start))

    def _write(self):
        self._operation = 'send_frame'


        if self._write_end is None:
            self._write_end = min(len(self._current), self._offset + WRITE_CHUNK_BYTES)
        view = memoryview(self._current)[self._offset:self._write_end]
        trace_call_started = time.monotonic() if self._stage_trace is not None else None
        try:
            self._counts['write_calls'] += 1
            count = self._socket.send(view)
        except ssl.SSLWantReadError:
            self._counts['write_want_read_count'] += 1
            self._write_want = 'read'; return
        except ssl.SSLWantWriteError:
            self._counts['write_want_write_count'] += 1
            self._write_want = 'write'; return
        except (BlockingIOError, InterruptedError):
            self._write_want = 'write'; return
        if count <= 0:
            raise ChannelError('write_error', 'send_frame', BrokenPipeError())
        self._offset += count
        self._write_progress_at = time.monotonic()
        self._write_end = None
        self._write_want = 'write'
        if self._stage_trace is not None:
            self.trace_stage('tls_ssl_accepted', **self._trace_current,
                frame_bytes=len(self._current), chunk_bytes=count, accepted_bytes=self._offset,
                elapsed_ms=max(0., (self._write_progress_at-self._write_started)*1000),
                call_elapsed_ms=max(0., (self._write_progress_at-trace_call_started)*1000),
                **self._trace_tcp_details())
        if self._offset == len(self._current):
            if self._stage_trace is not None:
                self.trace_stage('tls_send_complete', **self._trace_current,
                    frame_bytes=len(self._current), accepted_bytes=self._offset,
                    elapsed_ms=max(0., (self._write_progress_at-self._write_started)*1000),
                    queue_elapsed_ms=max(0., (self._write_progress_at-self._queued_at)*1000),
                    **self._trace_tcp_details())
                self._trace_current = None
            with self._changed:
                self._out_count -= 1
                self._out_bytes -= len(self._current)
                if self._current_receipt is not None:
                    self._current_receipt.set()
                self._changed.notify_all()
            self._current_receipt = None
            self._current = None
            self._write_started = self._queued_at = None
            self._write_progress_at = None

    def _deadlines(self):
        now = time.monotonic()
        if self._finish and now-self._finish_started >= 1.:
            raise ChannelError('write_timeout', 'send_frame', TimeoutError(), timeout_kind='finish')
        if (self._handshaken_at is not None and not self._active.is_set()
                and now-self._handshaken_at >= self.initial_timeout):
            raise ChannelError('initial_timeout', 'recv_header', TimeoutError(), timeout_kind='initial')
        if self._frame_started is not None:
            deadlines = [(self._frame_started+self.frame_timeout, 'read_frame')]
            if self.read_idle_timeout is not None:
                deadlines.append((self._read_progress_at+self.read_idle_timeout, 'read_idle'))
            deadline, kind = min(deadlines)
            if now >= deadline:
                raise ChannelError('frame_timeout', 'recv_header' if self._length is None else 'recv_body',
                                   TimeoutError(), timeout_kind=kind)


        if self._current is not None:
            deadlines = [(self._write_started+self.write_timeout, 'write_frame'),
                         (self._queued_at+self.queue_timeout, 'queue')]
            if self.write_idle_timeout is not None:
                deadlines.append((self._write_progress_at+self.write_idle_timeout, 'write_idle'))
            deadline, kind = min(deadlines)
            if now >= deadline:
                raise ChannelError('write_timeout', 'send_frame', TimeoutError(), timeout_kind=kind)
        with self._lock:
            if self._outgoing and now-self._outgoing[0][1] >= self.queue_timeout:
                raise ChannelError('write_timeout', 'queue', TimeoutError(), timeout_kind='queue')

    def _reject_owned(self):


        deadline, offset, want = time.monotonic()+1., 0, 'write'
        while not self._stop.is_set() and offset < len(self._rejection_frame):
            if time.monotonic() >= deadline:
                return
            try:
                r, w = self._select(want == 'read', want == 'write', min(.05, max(0, deadline-time.monotonic())))
                if not (r or w):
                    continue
                count = self._socket.send(memoryview(self._rejection_frame)[offset:])
                if count <= 0:
                    return
                offset += count
                want = 'write'
            except ssl.SSLWantReadError:
                want = 'read'
            except (ssl.SSLWantWriteError, BlockingIOError, InterruptedError):
                want = 'write'
            except OSError:
                return

    def _close_notify(self):
        





        if self._handshaken_at is None or (self.error is not None and self.error.code != 'peer_closed'):
            self.shutdown_status = 'skipped_after_error'
            return
        self._operation = 'shutdown'
        deadline = time.monotonic() + .5
        while time.monotonic() < deadline:
            try:
                self._socket.unwrap()
                self.shutdown_status = 'complete'
                return
            except ssl.SSLWantReadError:
                want = 'read'
            except (ssl.SSLWantWriteError, BlockingIOError, InterruptedError):
                want = 'write'
            except (OSError, ValueError):
                self.shutdown_status = 'incomplete'
                return
            try:

                select.select([self._socket] if want == 'read' else [],
                              [self._socket] if want == 'write' else [], [],
                              min(.05, max(0., deadline-time.monotonic())))
            except (OSError, ValueError):
                self.shutdown_status = 'incomplete'
                return
        self.shutdown_status = 'timeout'

    def _run(self):
        self.owner_ident = threading.get_ident()
        try:
            if self._stop.is_set():
                return
            self._raw.setblocking(False)
            self._operation = 'tls_handshake'
            self._socket = self._context.wrap_socket(self._raw, server_side=self._server_side,
                server_hostname=self._hostname, do_handshake_on_connect=False, suppress_ragged_eofs=False)
            self._socket.setblocking(False)
            self._handshake()
            while not self._stop.is_set():
                now = time.monotonic()
                if self._owner_loop_at is not None:
                    self._owner_loop_gap_max = max(self._owner_loop_gap_max, now-self._owner_loop_at)
                self._owner_loop_at = now
                self._apply_activation()
                self._take_output()
                if self._finish and self._current is None:
                    break
                self._deadlines()
                can_read = self._can_read()
                if not can_read and self._active.is_set():
                    if self._read_paused_at is None:
                        self._read_paused_at = now
                elif self._read_paused_at is not None:
                    self._read_pause_max = max(self._read_pause_max, now-self._read_paused_at)
                    self._read_paused_at = None
                need_read = (can_read and self._read_want == 'read') or (self._current is not None and self._write_want == 'read')
                need_write = (can_read and self._read_want == 'write') or (self._current is not None and self._write_want == 'write')
                self._operation = 'select'
                buffered = can_read and self._socket.pending() > 0
                try:
                    readable, writable = self._select(need_read, need_write, .05, buffered=buffered)
                except InterruptedError:
                    continue
                if self._stop.is_set():
                    break
                if self._current is not None and (readable if self._write_want == 'read' else writable):
                    self._write()
                if self._stop.is_set():
                    break
                if can_read and (readable if self._read_want == 'read' else writable):
                    self._read()
        except ChannelError as exc:
            if exc.code != 'stopped':
                if (exc.code == 'frame_length' and not self._active.is_set()
                        and self._rejection_frame is not None and self.ready.is_set()):
                    self._reject_owned()
                self._record(exc)
        except Exception as exc:
            self._record(ChannelError('io_error', self._operation, exc))
        finally:


            wire = self._socket if self._socket is not None else self._raw
            try:
                self._close_notify()
                self._operation = 'shutdown'
                wire.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                try:
                    self._operation = 'close'
                    wire.close()
                except OSError:
                    pass
                self._close_wakeup()
                with self._changed:
                    self._stop.set()
                    self.done.set()
                    self._changed.notify_all()
