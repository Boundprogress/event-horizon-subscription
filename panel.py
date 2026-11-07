#!/usr/bin/env python3

from __future__ import annotations
import argparse
import sys
if sys.platform != "win32":
    import fcntl
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid
import webbrowser

if sys.platform == "win32":
    import importlib.util as _win_import
    _win_spec = _win_import.spec_from_file_location("eh_win_platform", Path(__file__).resolve().with_name("win_platform.py"))
    win = _win_import.module_from_spec(_win_spec); _win_spec.loader.exec_module(win)
else:
    win = None

HERE = Path(__file__).resolve().parent
DEFAULT_ENDPOINT = 'https://api.plutoyyanng.cn'
MAX_BODY = 8192
ASSETS = {'/': ('panel.html', 'text/html; charset=utf-8'), '/terms': ('terms.html', 'text/html; charset=utf-8'), '/panel_i18n.js': ('panel_i18n.js', 'text/javascript; charset=utf-8'), '/panel.js': ('panel.js', 'text/javascript; charset=utf-8'), '/panel.css': ('panel.css', 'text/css; charset=utf-8')}
RECOVERY_OPS = {'email_request','email_verify','email_change_request','email_change_confirm','recovery_request','recovery_reset','recovery_manual_request','recovery_manual_confirm'}
CODE_OPS = {'email_code_request', 'email_code_verify', 'recovery_code_request', 'recovery_code_verify', 'recovery_code_reset', 'recovery_cancel'}
OPERATIONS = RECOVERY_OPS | {'redeem', 'prepare', 'activation_receipts', 'support_export', 'agent_export', 'update_check', 'update_apply', 'quit', 'register', 'login', 'logout', 'password', 'refresh', 'key_create', 'key_rotate', 'key_revoke', 'device_enroll', 'device_rotate', 'device_revoke', 'device_enable', 'check', 'diagnose', 'connect', 'disconnect', 'acknowledge'}
OPERATIONS.update({'agent_connect', 'terms_accept', 'recover_browser'})
OPERATIONS.update(CODE_OPS)
OPERATIONS.update({'appeals', 'appeal_create', 'appeal_release_unknown'})
AGENT_CONNECT_ERRORS = {'agent_connect_account_required', 'agent_connect_credentials_required',
    'agent_connect_account_changed', 'agent_connect_private_directory_required', 'agent_connect_write_failed',
    'unsupported_agent_host', 'installer_metadata_incomplete'}
ERRORS = {'email_not_verified','email_unchanged','account_recovery_requires_quiet','email_service_unavailable','email_queue_busy','email_rate_limited','invalid_email','email_proof_invalid_or_expired','email_already_verified','invalid_login','account_auth_rate_limited','session_not_found','request_not_found','forbidden','unauthorized','active_key_exists_rotate_required','active_key_changed_refresh_required','subscription_disabled','subscription_quota','subscription_not_started','invalid_credentials','username_taken','registration_closed','account_login_required','subscription_inactive','subscription_expired','quota_exhausted','api_key_limit','key_not_found','device_already_registered_rotate_if_credential_lost','device_not_registered','password_requires_12_to_128_characters','invalid_username','invalid_identifier','password_verification_busy','account_session_limit','wrong_password','password_changed','unknown_plan','account_disabled','invalid_password_encoding'}
CLEAN = {'verified_snapshot_stopped', 'observed_after_cleanup_error', 'not_started'}
ERRORS |= {'terms_required', 'terms_update_required', 'terms_document_unavailable', 'activation_code_invalid_or_unavailable', 'activation_request_conflict', 'activation_rate_limited', 'subscription_reactivation_review_required', 'subscription_plan_conflict', 'lifetime_frame_limit_exceeded'}
ERRORS |= {'email_code_invalid_or_expired', 'email_already_registered', 'email_in_use', 'email_unavailable', 'email_verification_required', 'email_required', 'email_not_pending'}
ERRORS |= {'appeal_request_conflict','appeal_pending_exists','appeal_not_eligible','appeal_state_changed','appeal_rate_limited','invalid_appeal_reason','invalid_public_result'}


def sibling(name):
    spec = importlib.util.spec_from_file_location('eh_panel_' + name, HERE / (name + '.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


class PanelError(Exception):
    def __init__(self, code, status=409):
        super().__init__(code); self.code, self.status = code, status


def pairs(items):
    out = {}
    for k, v in items:
        if k in out: raise ValueError('duplicate')
        out[k] = v
    return out


def parse(raw):
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(value, dict): raise ValueError()
    return value


def fields(value, expected):
    if set(value) != set(expected): raise PanelError('invalid_fields', 400)


def text(value, maximum=128):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum: raise PanelError('invalid_fields', 400)
    return value


def identifier(value, *, session=False):
    pattern = r'[0-9a-f]{32}' if session else r'[A-Za-z0-9._-]{1,64}'
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise PanelError('invalid_request_reference', 400)
    return value



def diagnostic_summary(value):

    if not isinstance(value, dict): return {}
    result = {}
    enums = {'status': {'checked', 'failed'}, 'mode': {'online', 'offline'},
             'api_config': {'valid'}, 'device_config': {'valid'}, 'chrome': {'found'},
             'device_authentication': {'not_tested'},
             'error': {'diagnostic_deadline', 'diagnostic_failed'}}
    for key, allowed in enums.items():
        if isinstance(value.get(key), str) and value[key] in allowed: result[key] = value[key]
    for key in ('api_health_ok', 'connector_tls_verified', 'browser_started'):
        if type(value.get(key)) is bool: result[key] = value[key]
    code = value.get('api_http_status')
    if type(code) is int and 100 <= code <= 599: result['api_http_status'] = code
    return result


def cleanup_summary(value):
    if not isinstance(value, dict): return {}
    allowed = {
        'class': {'SetupError', 'TimeoutExpired', 'OSError', 'LauncherError', 'BrowserError'},
        'reason': {'ownership_file_changed', 'profile_changed', 'browser_root_exited_before_stop',
                   'browser_root_identity_changed', 'browser_tree_limit', 'process_observation_deadline',
                   'process_observation_failed', 'process_observation_invalid', 'process_exit_not_proven',
                   'browser_stop_unconfirmed', 'browser_descendants_unverified', 'ownership_check_failed',
                   'cleanup_io_failed', 'process_identity_changed', 'launcher_cleanup_error',
                   'profile_in_use', 'profile_in_use_or_unsafe_lock', 'profile_identity_changed',
                   'profile_exit_not_verified', 'browser_recovery_state_changed',
                   'browser_recovery_identity_unverified', 'unsafe_profile_directory', 'unsafe_profile_lock'},
    }
    return {key: value[key] for key, choices in allowed.items()
            if isinstance(value.get(key), str) and value[key] in choices}


def terms_document():
    try:
        return dict(sibling('account').local_terms(), available=True)
    except Exception:
        return {'available': False, 'error': 'terms_document_unavailable'}


def device_connection_rejected(connection):

    first = connection.get('first_error')
    return (connection.get('clean') is True and connection.get('running') is False
            and connection.get('status') == 'failed' and isinstance(first, dict)
            and first.get('reason') == 'hub_rejected_connection' and first.get('phase') == 'hello')


def lifetime_subscription(value):
    """Recognize the explicit non-expiring frame contract, never a missing date."""
    return (value.get('billing') == 'lifetime_frames' and value.get('metering') == 'frames'
            and 'expires_at' in value and value['expires_at'] is None
            and 'period_ends_at' in value and value['period_ends_at'] is None
            and type(value.get('frame_limit')) is int and value['frame_limit'] > 0)


def onboarding(state, now=None):

    now = time.time() if now is None else now
    cloud = state.get('cloud')
    c = state.get('connection') or {}
    if not state['signed_in']: stage = 'login'
    elif state.get('pending'): stage = 'review_operation'
    elif c.get('clean') is False and not c.get('running'): stage = 'review_connection'
    elif not cloud or not state.get('cloud_checked_at') or now - state['cloud_checked_at'] > 300: stage = 'refresh'
    else:
        sub = cloud['subscription']; keys = [k for k in cloud['keys'] if not k.get('revoked')]
        local = state['credentials']; device = cloud['device']
        if cloud.get('terms', {}).get('current') is False: stage = 'terms'
        elif cloud.get('activation_review_required') is True: stage = 'activation_review'
        elif sub.get('enabled') is not True: stage = 'activation'
        elif not lifetime_subscription(sub) and not isinstance(sub.get('expires_at'), (int, float)): stage = 'refresh'
        elif not lifetime_subscription(sub) and sub['expires_at'] <= now: stage = 'expired'
        elif type(sub.get('remaining')) is not int: stage = 'refresh'
        elif sub['remaining'] <= 0: stage = 'quota'
        elif not keys: stage = 'recover_key' if local['api_ready'] else 'create_key'
        elif not local['api_ready'] or len(keys) != 1 or keys[0].get('id') != local['key_id']: stage = 'recover_key'
        elif device.get('registered') is not True: stage = 'recover_device' if local['device_ready'] else 'enroll_device'
        elif not local['device_ready']: stage = 'recover_device'
        elif device.get('enabled') is not True: stage = 'enable_device'
        elif c.get('status') == 'connected' and c.get('running'): stage = 'agent'
        elif c.get('running') or c.get('status') == 'starting': stage = 'connecting'
        elif device_connection_rejected(c): stage = 'review_device_connection'
        else: stage = 'connect'
    return {'stage': stage, 'host_connection': 'not_verified', 'automatic_actions': False}


class Store:

    def __init__(self, directory, endpoint):
        self.setup = sibling('setup')
        endpoint = self.setup.api_config({'endpoint': endpoint, 'token': 'anonymous-placeholder', 'timeout': 12})['endpoint']
        raw = Path(directory).expanduser().absolute()
        if raw.is_symlink(): raise PanelError('private_directory_required')
        if win: win.path_check(raw)
        self.root = raw.resolve()
        if self.root.is_relative_to(HERE): raise PanelError('keep_data_outside_package')
        if win: win.private_dir(self.root)
        else: self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = self.root.lstat()
        if not win and (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077): raise PanelError('private_directory_required')
        self.identity = st.st_dev, st.st_ino
        if win:
            self.lockfd = win.lock_file(self.root/'console.lock')
        else:
            self.lockfd = os.open(self.root/'console.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
            try:
                st = os.fstat(self.lockfd)
                if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode)!=0o600 or st.st_nlink!=1: raise PanelError('private_file_required')
                fcntl.flock(self.lockfd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except Exception:
                os.close(self.lockfd); self.lockfd = None; raise PanelError('console_already_running_or_unsafe_lock') from None
        try:
            file = self.root/'console.json'
            if file.exists() or file.is_symlink():
                self.data = self.setup.secure_json(file)
                if self.data.get('schema') != 1 or self.data.get('endpoint') != endpoint: raise PanelError('data_directory_endpoint_mismatch')
                for k in ('login_file','key_file','device_file'):
                    if self.data.get(k): self.credential(self.data[k])
            else:
                self.data = {'schema': 1, 'endpoint': endpoint, 'account': None, 'username': None, 'login_file': None, 'key_file': None, 'key_id': None, 'device_file': None, 'pending': None, 'connection': None}
                self.commit()
        except Exception:
            self.close(); raise

    def check(self):
        if win:
            win.private_dir(self.root, create=False)
            st=self.root.lstat()
            if (st.st_dev,st.st_ino)!=self.identity: raise PanelError('private_directory_changed')
            return
        st = self.root.lstat()
        if (st.st_dev,st.st_ino)!=self.identity or not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o077: raise PanelError('private_directory_changed')

    def write(self, name, value):
        self.check()
        if not re.fullmatch(r'[a-z0-9.-]+', name): raise PanelError('invalid_private_name')
        raw = (json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n').encode()
        if win: return win.atomic(self.root/name, raw)
        tmp = self.root/('tmp-'+uuid.uuid4().hex)
        fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd,'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
            self.check(); os.replace(tmp,self.root/name)
            d = os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try: os.fsync(d)
            finally: os.close(d)
        finally:
            if tmp.exists(): tmp.unlink()

    def commit(self): self.write('console.json', self.data)

    def credential(self, name):
        if not isinstance(name,str) or not re.fullmatch(r'credential-[a-f0-9]{32}\.json',name): raise PanelError('invalid_credential_reference')
        self.check(); return self.setup.secure_json(self.root/name)

    def save_credential(self, value):
        name = 'credential-'+uuid.uuid4().hex+'.json'; self.write(name,value); return name

    def close(self):
        if self.lockfd is not None: os.close(self.lockfd); self.lockfd=None


def remote(config, calls):

    request = json.dumps({'config':config,'calls':calls}).encode()
    try:
        done = subprocess.run([sys.executable,'-I','-S','-B',str(Path(__file__).resolve()),'_remote'],input=request,capture_output=True,timeout=16)
        if done.returncode or len(done.stdout)>13_000_000: raise ValueError()
        result = json.loads(done.stdout)
        if not isinstance(result,list) or len(result)!=len(calls): raise ValueError()
        return result
    except Exception:
        return [{'value':{},'status':None} for _ in calls]


def remote_child():
    q = parse(sys.stdin.buffer.read(32769))
    client = sibling('client'); result=[]
    for c in q['calls']:
        value,status = client.request(q['config'],c['method'],c['path'],c.get('body'))
        result.append({'value':value,'status':status})
    sys.stdout.write(json.dumps(result))


class Connection:
    def __init__(self, setup):
        self.setup=setup; self.proc=None; self.thread=None; self.lock=threading.Lock(); self.last={}; self.directory=None

    def start(self, api, device, directory, *, chrome=None, headless=False, reuse_profile=False):
        if self.proc is not None: raise PanelError('connection_already_started')
        self.directory=directory
        args=[sys.executable,'-I','-S','-B',str(HERE/'setup.py'),'run','--api-config',str(api),'--device-config',str(device),'--directory',str(directory)]
        if chrome: args+=['--chrome',chrome]
        if headless: args+=['--headless']
        if reuse_profile: args+=['--reuse-profile']
        self.last={'status':'starting'}
        self.proc=subprocess.Popen(args,stdin=subprocess.PIPE if win else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=dict(os.environ,EH_STOP_STDIN="1") if win else None)
        self.thread=threading.Thread(target=self.read,name='eh-console-setup-output',daemon=True);self.thread.start()

    def read(self):
        with self.proc.stdout as stream:
            while True:
                line=stream.readline(65537)
                if not line: break
                if len(line)>65536:
                    while line and not line.endswith(b'\n'): line=stream.readline(65537)
                    continue
                try:
                    v=parse(line); safe={}
                    if v.get('status') in {'starting','connected','stopped','failed'}: safe['status']=v['status']
                    if v.get('browser_cleanup') in CLEAN|{'unknown'}: safe['browser_cleanup']=v['browser_cleanup']
                    if isinstance(v.get('first_error'),dict): safe['first_error']=self.setup.first_error_summary(v['first_error'])
                    diagnostic = cleanup_summary(v.get('browser_cleanup_diagnostic'))
                    if diagnostic: safe['browser_cleanup_diagnostic'] = diagnostic
                    if 'error' in v: safe['error']='connection_failed'
                    if safe:
                        with self.lock:self.last=safe
                except Exception: pass

    def snapshot(self):
        with self.lock: v=dict(self.last)
        if self.proc:
            code=self.proc.poll();v['running']=code is None
            if code is not None:
                if self.thread and self.thread.ident is not None:self.thread.join(timeout=.2)
                with self.lock:v=dict(self.last)
                v['running']=False;v['exit_code']=code
                v['clean']=v.get('browser_cleanup') in CLEAN
                if not v['clean']:v['status']='cleanup_unknown'
        return v

    def stop(self):
        if not self.proc:return self.snapshot()
        if self.proc.poll() is None:
            if win:
                try: self.proc.stdin.write(b'stop\n');self.proc.stdin.flush();self.proc.stdin.close()
                except (OSError,ValueError): pass
            else: self.proc.send_signal(signal.SIGTERM)
        try:self.proc.wait(timeout=45)
        except subprocess.TimeoutExpired:
            with self.lock:self.last={'status':'cleanup_unknown'}
        return self.snapshot()


class UpdateBridge:

    def __init__(self, launcher=None, root=None, notice=None):
        self.launcher=launcher;self.root=root;self.lock=threading.Lock()
        self.source_manual=launcher is None and root is None
        if self.source_manual:self.value={'status':'source_manual'}
        elif launcher and root:self.value=dict(notice) if notice else {'status':'idle'}
        else:self.value={'status':'installer_required'}
        self.worker=None

    def snapshot(self):
        with self.lock:return dict(self.value)

    def check(self):
        if self.source_manual:raise PanelError('source_update_manual')
        if not self.launcher or not self.root:raise PanelError('new_installer_required')
        with self.lock:
            if self.worker and self.worker.is_alive():return {'status':'checking'}
            self.value={'status':'checking'}
            self.worker=threading.Thread(target=self._check,daemon=False);self.worker.start()
        return {'status':'checking'}

    def _check(self):
        try:
            run=subprocess.run([sys.executable,'-I','-S','-B',self.launcher,'--root',self.root,'--action','check','--no-open'],
                capture_output=True,timeout=40,**({'creationflags':subprocess.CREATE_NO_WINDOW} if win else {}))
            value=parse(run.stdout)
            if run.returncode:
                code=value.get('error','update_check_failed')
                if not isinstance(code,str) or not re.fullmatch(r'[a-z0-9_]{1,100}',code):code='update_check_failed'
                value={'status':'failed','error':code}
            elif value.get('status') not in {'available','up_to_date'} or not isinstance(value.get('version'),str) or type(value.get('sequence')) is not int:
                raise ValueError('invalid update result')
        except Exception:value={'status':'failed','error':'update_check_failed'}
        with self.lock:self.value=value


class Console:
    def __init__(self,store,*,chrome=None,headless=False,remote_fn=remote,updates=None):
        self.store=store;self.setup=store.setup;self.remote=remote_fn;self.chrome=chrome;self.headless=headless
        self.last_diagnostic=None


        self.email_code_flow=None;self.recovery_code_flow=None
        self.appeal_confirmation=None
        self.lock=threading.Lock();self.connection=Connection(self.setup);self.cloud=None;self.cloud_at=None;self.notice=None;self.quit_requested=False;self.update_requested=False;self.updates=updates or UpdateBridge()
        self.shutdown_result=None;self.shutdown_reply_pending=False
        if store.data.get('connection') and not store.data['connection'].get('clean'):
            self.notice='previous_connection_unconfirmed'

    def config(self,kind):
        name=self.store.data.get(kind+'_file')
        if not name:raise PanelError('login_required' if kind=='login' else 'credentials_required')
        value=self.setup.api_config(self.store.credential(name)) if kind in {'login','key'} else self.store.credential(name)
        if kind in {'login','key'} and value['endpoint']!=self.store.data['endpoint']:raise PanelError('credential_endpoint_mismatch')
        return value

    def browser_directory(self):

        self.store.check()
        account = text(self.store.data.get('account'))
        endpoint = urlsplit(self.store.data['endpoint'])
        host = endpoint.hostname.encode('idna').decode('ascii').lower()
        origin = [endpoint.scheme.lower(), host,
                  endpoint.port if endpoint.port is not None else (443 if endpoint.scheme == 'https' else 80)]
        namespace = json.dumps(['eh-browser-account-v1', origin, account],
                               ensure_ascii=True, separators=(',', ':')).encode()
        return self.store.root / ('browser-account-' + hashlib.sha256(namespace).hexdigest())

    def disconnected(self):
        self.sync_connection()
        v=self.store.data.get('connection')
        if v and not v.get('clean'):raise PanelError('disconnect_or_review_previous_connection')

    def recover_browser(self):
        self.sync_connection()
        previous = self.store.data.get('connection') or {}
        if (previous.get('running') is True
                or (self.connection.proc is not None and self.connection.proc.poll() is None)):
            raise PanelError('browser_recovery_connection_running')
        if previous.get('clean') is True:
            return {'status': 'already_clean', 'connection': previous, 'automatic_reconnect': False}
        self.store.check()
        raw = previous.get('directory')
        if not isinstance(raw, str): raise PanelError('browser_recovery_directory_unverified')
        directory = Path(raw)
        if (not directory.is_absolute() or directory.parent != self.store.root
                or not re.fullmatch(r'browser-(?:[a-f0-9]{32}|account-[a-f0-9]{64})', directory.name)
                or directory.is_symlink()):
            raise PanelError('browser_recovery_directory_unverified')
        browser = self.setup.sibling('browser')
        try:
            result = browser.reconcile_stopped(directory / 'ownership.json')
        except (browser.BrowserError, OSError, ValueError):
            raise PanelError('browser_recovery_unconfirmed') from None
        if not isinstance(result, dict) or result.get('status') != 'stopped':
            raise PanelError('browser_recovery_unconfirmed')
        recovered = dict(previous, status='stopped', running=False, clean=True,
                         browser_cleanup='verified_snapshot_stopped')
        self.store.data['connection'] = recovered
        try: self.store.commit()
        except Exception:
            self.store.data['connection'] = previous
            raise
        self.connection = Connection(self.setup)
        self.notice = None
        return {'status': 'recovered', 'connection': recovered, 'automatic_reconnect': False}

    def sync_connection(self):
        if self.connection.proc:
            v=self.connection.snapshot()
            if v.get('running') is False and v!=self.store.data.get('connection'):
                self.store.data['connection']=dict(v,directory=str(self.connection.directory));self.store.commit()
                if v.get('clean'):self.connection=Connection(self.setup)
            return v
        return self.store.data.get('connection') or {'status':'offline','clean':True,'running':False}

    def snapshot(self):
        d=self.store.data;c=self.sync_connection()
        value = {'endpoint':d['endpoint'],'version':(HERE/'VERSION').read_text().strip() if (HERE/'VERSION').exists() else (HERE.parent/'VERSION').read_text().strip(),
                'username':d.get('username'),'signed_in':bool(d.get('login_file')),'account':d.get('account'),
                'credentials':{'api_ready':bool(d.get('key_file')),'device_ready':bool(d.get('device_file')),'key_id':d.get('key_id'),
                    'api_path':str(self.store.root/d['key_file']) if d.get('key_file') else None},
                'connection':c,'cloud':self.cloud,'cloud_checked_at':self.cloud_at,'pending':d.get('pending'),
                'notice':self.notice,'payment':'not_configured','updates':self.updates.snapshot(),
                'terms_document':terms_document()}
        value['onboarding'] = onboarding(value)
        value['email_verification'] = self.code_status('email')
        value['account_recovery'] = self.code_status('recovery')
        uncertain=d.get('appeal_unconfirmed')
        value['appeal_unconfirmed']={k:uncertain[k] for k in ('request_id','started_at') if k in uncertain} if isinstance(uncertain,dict) and uncertain.get('account')==d.get('account') and d.get('login_file') else None
        return value

    def code_status(self, kind):
        attribute = 'email_code_flow' if kind == 'email' else 'recovery_code_flow'
        flow = getattr(self, attribute)
        if flow and (flow['expires_at'] <= time.time() or (kind == 'email' and flow.get('account') != self.store.data.get('account'))):
            setattr(self, attribute, None);flow = None
        result = {'stage': flow['stage'] if flow else 'request'}
        if flow:
            result['expires_at'] = flow['expires_at']
            if kind == 'recovery' and flow['stage'] == 'reset': result['username'] = flow['username']
        return result

    def forget_identity(self):
        self.store.data.update(account=None, username=None, login_file=None,
                               key_file=None, key_id=None, device_file=None)
        self.cloud=None;self.cloud_at=None;self.last_diagnostic=None;self.notice=None
        self.email_code_flow=None
        self.appeal_confirmation=None
        self.store.commit()

    def code_operation(self, op, body):

        if self.store.data.get('pending'): raise PanelError('previous_operation_requires_review')
        self.disconnected()
        if op == 'recovery_cancel':
            fields(body,set());self.recovery_code_flow=None
            return {'status':'recovery_restarted'}
        recovery = op.startswith('recovery_')
        attribute = 'recovery_code_flow' if recovery else 'email_code_flow'
        self.code_status('recovery' if recovery else 'email')
        cfg = {'endpoint':self.store.data['endpoint'],'token':'anonymous-placeholder','timeout':12} if recovery else self.config('login')
        request = op.endswith('_request')
        reset = op == 'recovery_code_reset'
        if request:
            fields(body, {'email'} if recovery else set())
            if recovery: text(body['email'],254)
            setattr(self, attribute, None)
            path = '/account/recovery/code/request' if recovery else '/account/email/code/request'
            payload = dict(body)
        else:
            flow = getattr(self, attribute)
            if not flow: raise PanelError('email_code_invalid_or_expired',400)
            if reset:
                fields(body,{'new_password'});text(body['new_password'],128)
                if flow['stage'] != 'reset': raise PanelError('email_code_invalid_or_expired',400)
                payload = {'token':flow['reset_token'],'new_password':body['new_password']}
                path = '/account/recovery/reset'


                self.forget_identity()
                self.recovery_code_flow=None
            else:
                fields(body,{'code'})
                if not isinstance(body['code'],str) or not re.fullmatch(r'[0-9]{6}',body['code']):
                    raise PanelError('email_code_invalid_or_expired',400)
                if flow['stage'] != 'code': raise PanelError('email_code_invalid_or_expired',400)
                payload = {'challenge':flow['challenge'],'code':body['code']}
                path = '/account/recovery/code/verify' if recovery else '/account/email/code/verify'
        response = None
        try:
            response = self.remote(cfg,[{'method':'POST','path':path,'body':payload}])[0]
            value = self.result(response)
            if request:
                challenge = value.get('challenge');expires = value.get('expires_in')
                if (value.get('status') != 'email_request_accepted' or not isinstance(challenge,str)
                        or not re.fullmatch(r'ehc_[A-Za-z0-9_-]{43}',challenge)
                        or type(expires) is not int or not 1 <= expires <= 900):
                    raise PanelError('response_unknown_check_remote_state')
                setattr(self,attribute,{'stage':'code','challenge':challenge,'expires_at':time.time()+expires,
                                        'account':self.store.data.get('account')})
                return {'status':'email_request_accepted'}
            if reset:
                if value.get('status') != 'password_changed' or value.get('login_required') is not True:
                    raise PanelError('response_unknown_check_remote_state')
                return {'status':'password_changed','login_required':True}
            if recovery:
                token = value.get('reset_token');expires = value.get('expires_in');name = value.get('username')
                if (value.get('status') != 'email_code_verified' or not isinstance(token,str)
                        or not re.fullmatch(r'ehr_[A-Za-z0-9_-]{43}',token)
                        or type(expires) is not int or not 1 <= expires <= 300
                        or not isinstance(name,str) or not 1 <= len(name) <= 64):
                    raise PanelError('response_unknown_check_remote_state')
                self.recovery_code_flow={'stage':'reset','reset_token':token,'username':name,'expires_at':time.time()+expires}
                return {'status':'email_code_verified','username':name}
            if value.get('status') != 'email_verified': raise PanelError('response_unknown_check_remote_state')
            self.email_code_flow=None;self.cloud=None;self.cloud_at=None
            return {'status':'email_verified'}
        except Exception as exc:
            rejected = isinstance(response,dict) and type(response.get('status')) is int and 400 <= response['status'] < 500
            if not rejected:
                setattr(self,attribute,None)
                raise PanelError('recovery_response_unknown_restart' if recovery else 'email_response_unknown_restart') from None
            raise

    def call(self,kind,path,body=None):
        config=self.config('login')
        return self.remote(config,[{'method':kind,'path':path,'body':body}])[0]

    def result(self,response):
        status=response.get('status');v=response.get('value')
        if status is None:raise PanelError('response_unknown_check_remote_state')
        if type(status) is not int or not isinstance(v,dict):raise PanelError('response_unknown_check_remote_state')
        if not 200<=status<300:
            code=v.get('error');raise PanelError(code if isinstance(code,str) and code in ERRORS else 'remote_request_rejected',status if 400<=status<=599 else 502)
        return v

    def refresh(self):
        self.cloud=None;self.cloud_at=None
        responses=self.remote(self.config('login'),[{'method':'GET','path':'/account/'+p} for p in ('me','keys','device')])
        me,keys,device=[self.result(v) for v in responses]
        if me.get('account')!=self.store.data['account']:raise PanelError('account_identity_mismatch')

        subscription=me.get('subscription',{});policy=subscription.get('policy',{});usage=subscription.get('period_usage',{})
        sub={k:v for k,v in policy.items() if k in {'enabled','expires_at','command_limit','max_sessions','max_commands','period_starts_at','period_ends_at','frame_limit','price_minor','unit_price_minor'} and type(v) in (bool,int,float,type(None))}
        if policy.get('billing') == 'calendar_month':
            sub.update(billing='calendar_month', billing_timezone='Asia/Shanghai')
        elif policy.get('billing') == 'lifetime_frames':
            if not lifetime_subscription(policy): raise PanelError('invalid_remote_response')
            sub.update(billing='lifetime_frames')
        sub['metering'] = 'frames' if policy.get('metering') == 'frames' else 'commands'
        if policy.get('currency') == 'CNY': sub['currency'] = 'CNY'
        sub.update({k:v for k,v in usage.items() if k in {'admitted','reserved','finished','remaining','charged_frames','reserved_frames'} and type(v) is int})
        if 'enabled' in sub:sub['enabled']=bool(sub['enabled'])
        rows=keys.get('keys',[])
        if not isinstance(rows,list) or len(rows)>128:raise PanelError('invalid_remote_response')
        self.cloud={'subscription':sub,'keys':[{k:x.get(k) for k in ('id','label','created','revoked') if type(x.get(k)) in (str,int,float,bool,type(None))} for x in rows if isinstance(x,dict)],
                    'device':{k:device.get(k) for k in ('device','registered','enabled') if type(device.get(k)) in (str,bool)},'plan_id':me.get('plan_id') if isinstance(me.get('plan_id'),str) else None,
                    'entry_policy':sibling('example_agent').entry_policy(me.get('entry_policy')),
                    'activation_review_required':me.get('activation_review_required') is True}
        terms = me.get('terms')
        if isinstance(terms, dict):
            self.cloud['terms'] = {k: terms.get(k) for k in ('version', 'sha256', 'accepted_version', 'accepted_at', 'current')
                                   if type(terms.get(k)) in (str, bool, int, float, type(None))}
        recovery = me.get('recovery', {})
        self.cloud['recovery'] = {'available':recovery.get('available') is True, 'verified':recovery.get('verified') is True,
            'email_masked':recovery.get('email_masked') if isinstance(recovery.get('email_masked'), str) and len(recovery['email_masked']) <= 254 else None,
            'pending_verification':recovery.get('pending_verification') is True,
            'pending_email_masked':recovery.get('pending_email_masked') if isinstance(recovery.get('pending_email_masked'),str) and len(recovery['pending_email_masked']) <= 254 else None}
        appeals = me.get('appeals', {})
        self.cloud['appeals'] = {'available':isinstance(me.get('appeals'),dict) and type(appeals.get('eligible')) is bool,
                                'eligible':appeals.get('eligible') is True,
                                'contact_email':self.appeal_contact(appeals.get('contact_email')),
                                'pending_id':appeals.get('pending_id') if isinstance(appeals.get('pending_id'),str) and re.fullmatch(r'[A-Za-z0-9._-]{1,64}',appeals['pending_id']) else None}
        self.cloud_at=time.time();self.notice=None
        return {'status':'refreshed'}

    @staticmethod
    def activation_receipt(value):

        if not isinstance(value, dict): raise PanelError('invalid_remote_response')
        result = {}
        for key in ('activation_id', 'request_id', 'plan_id'):
            result[key] = text(value.get(key), 128)
        lifetime = value.get('billing') == 'lifetime_frames'
        if type(value.get('frames')) is not int or value['frames'] <= 0: raise PanelError('invalid_remote_response')
        if type(value.get('months')) is not int: raise PanelError('invalid_remote_response')
        if lifetime:
            if (value['months'] != 0 or value['plan_id'] != 'eh_lifetime'
                    or type(value.get('total_frames')) is not int or value['total_frames'] != value['frames']):
                raise PanelError('invalid_remote_response')
            result.update(billing='lifetime_frames', total_frames=value['total_frames'])
        elif value['months'] <= 0:
            raise PanelError('invalid_remote_response')
        result.update(months=value['months'], frames=value['frames'])
        stamp = value.get('redeemed_at')
        if type(stamp) not in (int, float) or not 0 < stamp < 1e12: raise PanelError('invalid_remote_response')
        result['redeemed_at'] = stamp
        return result

    def activation_receipts(self):
        value = self.result(self.call('GET', '/account/activation/receipts'))
        rows = value.get('receipts')
        if not isinstance(rows, list) or len(rows) > 10000: raise PanelError('invalid_remote_response')
        receipts = [self.activation_receipt(row) for row in rows]
        pending = self.store.data.get('pending') or {}
        confirmed = pending.get('operation') == 'redeem' and any(row['request_id'] == pending.get('request_id') for row in receipts)

        return {'receipts': receipts, 'pending_confirmed': confirmed}

    def prepare(self):

        if self.store.data.get('pending'): raise PanelError('previous_operation_requires_review')
        self.disconnected()
        self.refresh()
        for _ in range(3):
            stage = self.snapshot()['onboarding']['stage']
            if stage == 'create_key':
                self.mutation('key_create', {'label': 'local-client'})
            elif stage == 'enroll_device':

                try: self.config('key')
                except Exception: return {'status': 'needs_attention', 'stage': 'recover_key'}
                self.mutation('device_enroll', {})
            elif stage == 'connect':
                try: self.config('key')
                except Exception: return {'status': 'needs_attention', 'stage': 'recover_key'}
                try:
                    device = sibling('connector').validate_config(self.config('device'))
                    if device['device'] != self.cloud['device'].get('device'):
                        return {'status': 'needs_attention', 'stage': 'recover_device'}
                except Exception: return {'status': 'needs_attention', 'stage': 'recover_device'}
                return {'status': 'prepared', 'stage': 'connect'}
            else:
                return {'status': 'needs_attention', 'stage': stage}
            self.refresh()
        return {'status': 'needs_attention', 'stage': self.snapshot()['onboarding']['stage']}

    def support_export(self):
        c = self.sync_connection();d = self.store.data
        status = c.get('status')
        connection = {'status': status if status in {'offline','starting','connected','stopped','failed','cleanup_unknown'} else 'unknown'}
        for key in ('running', 'clean'):
            if type(c.get(key)) is bool: connection[key] = c[key]
        if c.get('browser_cleanup') in CLEAN | {'unknown'}: connection['browser_cleanup'] = c['browser_cleanup']
        connection['has_error'] = bool(c.get('first_error') or c.get('error'))


        first = c.get('first_error')
        if isinstance(first, dict):
            labels = {key: first[key] for key, allowed in
                      (('reason', {'hub_rejected_connection', 'browser_ownership_lost', 'browser_not_running',
                                   'browser_ownership_unverified', 'browser_ownership_changed',
                                   'browser_profile_changed', 'browser_endpoint_changed', 'browser_lock_changed',
                                   'invalid_browser_identity', 'invalid_browser_launch_args'}),
                       ('phase', {'hello', 'lifecycle', 'ownership'}))
                      if isinstance(first.get(key), str) and first[key] in allowed}
            if labels: connection['first_error'] = labels
        diagnostic = cleanup_summary(c.get('browser_cleanup_diagnostic'))
        if diagnostic: connection['browser_cleanup_diagnostic'] = diagnostic

        report = {'schema': 'eh-support/1', 'generated_at': time.time(),
                  'version': self.snapshot()['version'], 'platform': sys.platform,
                  'signed_in': bool(d.get('login_file')),
                  'credentials_present': {'api': bool(d.get('key_file')), 'device': bool(d.get('device_file'))},
                  'connection': connection, 'account_operation_unconfirmed': bool(d.get('pending')),
                  'last_diagnostic': self.last_diagnostic,
                  'scope': 'local_status_only_no_task_content'}
        return {'report': report}

    @staticmethod
    def appeal_contact(value):
        return value if isinstance(value,str) and len(value)<=254 and re.fullmatch(r"[^\s<>\x00-\x1f\x7f]+@[^\s<>\x00-\x1f\x7f]+",value) else None

    @staticmethod
    def appeal_record(value):
        if not isinstance(value,dict):raise PanelError('invalid_remote_response')
        row={}
        for key in ('id','request_id'):
            row[key]=text(value.get(key),64)
            if not re.fullmatch(r'[A-Za-z0-9._-]{1,64}',row[key]):raise PanelError('invalid_remote_response')
        if value.get('status') not in {'pending','restored','rejected','closed'}:raise PanelError('invalid_remote_response')
        row['status']=value['status']
        for key,maximum in [('reason',1000),('public_result',500)]:
            item=value.get(key,'')
            if not isinstance(item,str) or len(item)>maximum:raise PanelError('invalid_remote_response')
            row[key]=item
        for key in ('created_at','updated_at','resolved_at'):
            item=value.get(key)
            if item is not None and (type(item) not in (int,float) or not math.isfinite(item) or item<0):raise PanelError('invalid_remote_response')
            row[key]=item
        if type(value.get('version')) is not int or value['version']<1:raise PanelError('invalid_remote_response')
        row['version']=value['version']
        return row

    def appeal_list(self, request_id=None):
        pending=self.store.data.get('pending') or {}
        path='/account/appeals'
        if pending.get('operation')=='appeal_create':
            reference=identifier(pending.get('request_id'))
            path+='?request_id='+reference
        elif request_id is not None:path+='?request_id='+identifier(request_id)
        response=self.call('GET',path)
        if response.get('status')==404:raise PanelError('appeals_service_update_required')
        value=self.result(response)
        rows=value.get('appeals')
        if not isinstance(rows,list) or len(rows)>20:raise PanelError('invalid_remote_response')
        rows=[self.appeal_record(row) for row in rows]
        uncertain=self.store.data.get('appeal_unconfirmed')
        if isinstance(uncertain,dict) and uncertain.get('account')==self.store.data.get('account') and any(row['request_id']==uncertain.get('request_id') and row['status']!='pending' for row in rows):
            self.store.data['appeal_unconfirmed']=None;self.store.commit()
        confirmed=pending.get('operation')=='appeal_create' and any(row['request_id']==pending.get('request_id') for row in rows)
        self.appeal_confirmation=pending.get('id') if confirmed else None
        return {'appeals':rows,'eligible':value.get('eligible') is True,
                'contact_email':self.appeal_contact(value.get('contact_email')),
                'pending_confirmed':confirmed}

    def mutation(self,op,body):
        d=self.store.data
        if d.get('pending'):raise PanelError('previous_operation_requires_review')
        pending={'id':uuid.uuid4().hex,'operation':op,'started_at':time.time(),'state':'sending'}
        if op in {'redeem','appeal_create'}: pending['request_id'] = pending['id']
        if op=='appeal_create': self.appeal_confirmation=None
        d['pending']=pending;self.store.commit()
        response=None;dispatched=False;outcome={}
        def post(path, payload, config=None):
            nonlocal dispatched
            config=self.config('login') if config is None else config
            dispatched=True
            return self.remote(config,[{'method':'POST','path':path,'body':payload}])[0]
        try:
            if op in {'register','login'}:
                if op == 'register':


                    fields(body,{'username','password','email','terms_accepted','terms_version','terms_sha256'})
                    text(body['email'],254)
                    if body['terms_accepted'] is not True: raise PanelError('terms_required', 403)
                else:
                    fields(body,{'username','password'})
                text(body['username'],256);text(body['password'],128)
                cfg={'endpoint':d['endpoint'],'token':'anonymous-placeholder','timeout':12}
                if op == 'register':
                    terms_reply=self.remote(cfg,[{'method':'GET','path':'/account/terms'}])[0]
                    if isinstance(terms_reply,dict) and terms_reply.get('status')==404:


                        raise PanelError('service_update_required', 409)
                    terms=self.result(terms_reply)
                    try:
                        consent = sibling('account').confirmed_terms(terms, body['terms_version'], body['terms_sha256'])
                    except Exception as exc:
                        raise PanelError(str(exc) if str(exc) in ERRORS else 'terms_document_unavailable', 409) from None
                    body={'username':body['username'],'password':body['password'],'email':body['email'], **consent}
                response=post('/account/'+op,body,cfg);v=self.result(response)
                aid=text(v.get('account'));name=text(v.get('username'));token=text(v.get('token'),512)
                if not token.startswith('ehs_'):raise PanelError('invalid_remote_response')
                filename=self.store.save_credential(self.setup.api_config(dict(cfg,token=token)))
                if d.get('account')!=aid:
                    d.update(key_file=None,key_id=None,device_file=None)

                    if (d.get('connection') or {}).get('clean') is True:
                        d['connection']=None
                d.update(account=aid,username=name,login_file=filename);self.cloud=None;self.cloud_at=None;self.last_diagnostic=None
                self.email_code_flow=None;self.recovery_code_flow=None
                if op == 'register': outcome['email_verification_required'] = v.get('email_verification_required') is True
            elif op == 'appeal_create':
                fields(body,{'reason'});reason=text(body['reason'],1000).strip()
                if not reason or re.search(r'eh(?:ac|s|k|r|v|m|c)_[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY-----',reason):
                    raise PanelError('invalid_appeal_reason',400)
                response=post('/account/appeals',{'request_id':pending['request_id'],'reason':reason})
                v=self.result(response);row=self.appeal_record(v.get('appeal'))
                if row['request_id']!=pending['request_id'] or type(v.get('replayed')) is not bool:raise PanelError('response_unknown_check_remote_state')
                outcome={'status':'appeal_submitted','appeal':row,'replayed':v['replayed']}
                self.cloud=None;self.cloud_at=None
            elif op == 'terms_accept':
                fields(body, {'terms_version', 'terms_sha256', 'terms_accepted'})
                if body['terms_accepted'] is not True: raise PanelError('terms_required', 403)
                reply = self.call('GET', '/account/terms')
                if isinstance(reply, dict) and reply.get('status') == 404:
                    raise PanelError('service_update_required', 409)
                try:
                    consent = sibling('account').confirmed_terms(self.result(reply), body['terms_version'], body['terms_sha256'])
                except PanelError: raise
                except Exception as exc:
                    raise PanelError(str(exc) if str(exc) in ERRORS else 'terms_document_unavailable', 409) from None
                response = post('/account/terms/accept', consent)
                accepted = self.result(response)
                if accepted.get('current') is not True: raise PanelError('invalid_remote_response')
                self.cloud = None; self.cloud_at = None
                outcome = {'status':'terms_accepted', 'version':accepted.get('version')}
            elif op == 'redeem':
                fields(body, {'code'})
                code = text(body['code'], 128).strip()
                if not re.fullmatch(r'ehac_[A-Za-z0-9_-]{43}', code):
                    raise PanelError('activation_code_invalid_or_unavailable', 400)
                response = post('/account/activation/redeem', {'code': code, 'request_id': pending['request_id']})
                v = self.result(response)
                if type(v.get('applied')) is not bool: raise PanelError('invalid_remote_response')
                outcome = {'status': 'activated', 'applied': v['applied'], 'receipt': self.activation_receipt(v.get('receipt'))}
                self.cloud=None;self.cloud_at=None
            elif op in RECOVERY_OPS:
                required = {'email_request':{'email','password'}, 'email_verify':{'token'},
                    'recovery_request':{'username','email'}, 'recovery_reset':{'token','new_password'}, 'email_change_request':{'email','password'}, 'email_change_confirm':{'old_token','new_token'}, 'recovery_manual_request':{'ticket'}, 'recovery_manual_confirm':{'ticket','email_token','new_password'}}[op]
                fields(body, required)
                for field in required: text(body[field], 254 if field == 'email' else 128)
                cfg = {'endpoint':d['endpoint'],'token':'anonymous-placeholder','timeout':12} if op.startswith('recovery_') else None
                response=post('/account/'+op.replace('_','/'),body,cfg);self.result(response)
                if op in {'recovery_reset','email_change_confirm','recovery_manual_confirm'}:
                    d['login_file']=None;self.cloud=None;self.cloud_at=None;self.last_diagnostic=None
                    self.email_code_flow=None;self.recovery_code_flow=None
                    if op=='recovery_manual_confirm': d.update(key_file=None,key_id=None,device_file=None)
                elif op=='email_verify': self.cloud=None;self.cloud_at=None
            elif op in {'key_create','key_rotate'}:
                fields(body,{'key_id','label'} if op=='key_rotate' else {'label'});text(body['label'],64)
                if op=='key_rotate':text(body['key_id'],64)
                response=post('/account/keys/'+op.split('_')[1],body);v=self.result(response)
                cfg=self.config('login');token=text(v.get('token'),512);kid=text(v.get('key_id'))
                if not token.startswith('ehk_'):raise PanelError('invalid_remote_response')
                d['key_file']=self.store.save_credential(dict(cfg,token=token));d['key_id']=kid
            elif op in {'device_enroll','device_rotate'}:
                fields(body,set());response=post('/account/device/'+op.split('_')[1],{});v=self.result(response)
                cfg=sibling('connector').validate_config(v.get('device_config'))

                d['device_file']=self.store.save_credential(cfg)
                previous = d.get('connection') or {}
                if previous.get('clean') is True and not previous.get('running') and previous.get('status') == 'failed':
                    d['connection']=None
                self.notice=None if v.get('hub_applied') is True else 'device_waiting_for_hub'
            elif op=='key_revoke':
                fields(body,{'key_id'});text(body['key_id'])
                response=post('/account/keys/revoke',body);self.result(response)
                if body['key_id']==d.get('key_id'):d.update(key_file=None,key_id=None)
            elif op in {'device_revoke','device_enable'}:
                fields(body,set());response=post('/account/device/'+op.split('_')[1],{});v=self.result(response)
                self.notice=None if v.get('hub_applied') is True else 'device_waiting_for_hub'
            elif op in {'logout','password'}:
                fields(body,{'old_password','new_password'} if op=='password' else set())
                if op=='password':text(body['old_password'],128);text(body['new_password'],128)
                response=post('/account/'+op,body);self.result(response);d['login_file']=None;self.cloud=None;self.cloud_at=None;self.last_diagnostic=None
                self.email_code_flow=None;self.recovery_code_flow=None
            else:raise PanelError('unknown_operation',404)
            d['pending']=None;self.store.commit();return dict({'status':'saved','notice':self.notice}, **outcome)
        except Exception:
            if response is not None and type(response.get('status')) is int and 400<=response['status']<500:
                d['pending']=None
            elif not dispatched:

                d['pending']=None
            else:
                pending['state']='unknown';d['pending']=pending
            self.store.commit();raise

    def dispatch(self,op,body):
        if op not in OPERATIONS:raise PanelError('unknown_operation',404)
        if self.quit_requested:raise PanelError('client_closing')
        if op in CODE_OPS: return self.code_operation(op,body)
        if op=='appeals':
            if set(body) not in (set(),{'request_id'}):raise PanelError('invalid_fields',400)
            return self.appeal_list(body.get('request_id'))
        if op=='appeal_release_unknown':
            fields(body,{'operation_id','reviewed'});p=self.store.data.get('pending')
            if not p or p.get('operation')!='appeal_create' or p.get('id')!=body['operation_id'] or p.get('state')!='unknown' or body['reviewed'] is not True:raise PanelError('review_required')
            metadata={'request_id':identifier(p.get('request_id')),'started_at':p['started_at'],'reviewed_at':time.time(),'outcome':'unknown','account':self.store.data.get('account'),'automatic_retry':False}
            self.store.write('appeal-unknown-review.json',metadata)
            self.store.data['appeal_unconfirmed']=metadata;self.store.data['pending']=None;self.store.commit()
            return {'status':'appeal_still_unconfirmed','automatic_retry':False}
        if op=='appeal_create':
            self.config('login')
            if not self.cloud or self.cloud.get('appeals',{}).get('available') is not True:self.refresh()
            if self.cloud.get('appeals',{}).get('available') is not True:raise PanelError('appeals_service_update_required')
        if op=='support_export': fields(body,set());return self.support_export()
        if op=='agent_connect':
            if set(body) not in (set(), {'host'}) or body.get('host', 'generic') not in ('codex', 'generic'):
                raise PanelError('invalid_fields', 400)
            self.config('login');self.config('key')
            agent = sibling('example_agent')
            try:
                result = agent.prepare_agent_link(self.store.root, host=body.get('host', 'generic'),
                    updater=getattr(self.updates,'launcher',None), install_root=getattr(self.updates,'root',None))
            except agent.AgentError as exc:
                code = str(exc)
                raise PanelError(code if code in AGENT_CONNECT_ERRORS else 'agent_connect_write_failed') from None
            return dict(result, status='agent_link_ready', contains_credentials=False)
        if op=='agent_export':
            if set(body) not in (set(), {'host'}) or body.get('host', 'generic') not in ('codex', 'generic'):
                raise PanelError('invalid_fields', 400)
            self.config('login');self.config('key')
            result=sibling('example_agent').agent_bundle(self.store.root, host=body.get('host', 'generic'),
                updater=getattr(self.updates,'launcher',None), install_root=getattr(self.updates,'root',None))
            return dict(result, status='agent_config_ready', contains_credentials=False)
        if op=='update_check':fields(body,set());return self.updates.check()
        if op=='update_apply':
            fields(body,set())
            if self.updates.source_manual:raise PanelError('source_update_manual')
            self.disconnected()
            if self.store.data.get('pending'):raise PanelError('previous_operation_requires_review')
            if self.updates.snapshot().get('status')!='available':raise PanelError('check_update_first')
            self.update_requested=True;self.quit_requested=True;return {'status':'updating'}
        if op=='quit':
            fields(body,set())
            # dispatch already holds the console lock. Complete cleanup before
            # issuing a receipt, without recursively acquiring it via close().
            try:
                self.connection.stop()
                cleanup=self.sync_connection()
            except Exception:
                cleanup={'status':'cleanup_unknown','clean':False}
            clean=cleanup.get('clean') is True and cleanup.get('running') is not True
            self.shutdown_result=dict(cleanup,clean=clean)
            self.shutdown_reply_pending=True
            self.quit_requested=True
            return {'status':'shutdown_ready','connection_clean':clean}
        if op=='refresh':fields(body,set());return self.refresh()
        if op=='activation_receipts':fields(body,set());return self.activation_receipts()
        if op=='prepare':fields(body,set());return self.prepare()
        if op=='acknowledge':
            fields(body,{'operation_id','reviewed'})
            p=self.store.data.get('pending')
            if not p or body['operation_id']!=p['id'] or body['reviewed'] is not True:raise PanelError('review_required')
            if p['operation']=='appeal_create' and self.appeal_confirmation!=p['id']:raise PanelError('appeal_query_required')
            self.store.write('review-'+p['id']+'.json',dict(p,reviewed_at=time.time()))
            self.store.data['pending']=None;self.store.commit();return {'status':'review_recorded','automatic_retry':False}
        if op=='disconnect':fields(body,set());self.connection.stop();return {'connection':self.sync_connection()}
        if op=='recover_browser':fields(body,set());return self.recover_browser()
        if op in {'check','diagnose','connect'}:
            fields(body,set());self.config('login');self.config('key');self.config('device')
            api=self.store.root/self.store.data['key_file'];device=self.store.root/self.store.data['device_file']
            if op in {'check','diagnose'}:
                result=self.setup.check(api,device,self.chrome)
                result = self.setup.online_probe(api,device) if op=='diagnose' else result
                self.last_diagnostic={'checked_at':time.time(), **diagnostic_summary(result)}
                return result
            if self.store.data.get('pending'):raise PanelError('previous_operation_requires_review')
            self.disconnected();self.setup.check(api,device,self.chrome)
            directory=self.browser_directory()
            self.store.data['connection']={'status':'starting','clean':False,'directory':str(directory)};self.store.commit()
            try:self.connection.start(api,device,directory,chrome=self.chrome,headless=self.headless,reuse_profile=True)
            except Exception:
                if self.connection.proc is None:
                    self.store.data['connection']={'status':'failed','clean':True,'browser_cleanup':'not_started'}
                else:
                    self.connection.stop();self.store.data['connection']=dict(self.connection.snapshot(),directory=str(directory))
                self.store.commit();raise
            return {'status':'starting','automatic_reconnect':False}
        if op not in {'terms_accept','appeal_create'}: self.disconnected()
        return self.mutation(op,body)

    def safe_json(self,value):
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False)
        for kind in ('login','key','device'):
            name=self.store.data.get(kind+'_file')
            if name:
                token=self.store.credential(name).get('token')
                if isinstance(token,str) and token:raw=raw.replace(token,'[REDACTED]')
        return raw.encode()

    def close(self):
        self.email_code_flow=None;self.recovery_code_flow=None
        with self.lock:
            if self.shutdown_result is not None:return self.shutdown_result
            self.connection.stop();return self.sync_connection()


class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,app):
        self.app=app;self.capability=secrets.token_urlsafe(32)
        self.slots=threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1',0),handler)
        self.origin='http://127.0.0.1:'+str(self.server_address[1])
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):request.close();return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()
    def handle_error(self,*_):pass


class handler(BaseHTTPRequestHandler):
    server_version='EH-local';sys_version=''
    def setup(self):
        self.request.settimeout(5);super().setup()
    def log_message(self,*_):pass
    def reply(self,status,raw,ctype='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header('X-Frame-Options','DENY');self.send_header('Connection','close');self.end_headers();self.wfile.write(raw);self.close_connection=True
    def error(self,code,status=400):self.reply(status,json.dumps({'error':code}).encode())
    def boundary(self,api=False):
        if self.headers.get_all('Host')!=[self.server.origin[7:]]:raise PanelError('invalid_host',403)
        origin=self.headers.get_all('Origin')
        if origin is not None and origin!=[self.server.origin]:raise PanelError('invalid_origin',403)
        if self.headers.get('Sec-Fetch-Site') in {'cross-site','same-site'}:raise PanelError('cross_site_request',403)
        if api:
            headers=self.headers.get_all('Authorization')
            if not headers or len(headers)!=1 or not hmac.compare_digest(headers[0],'Bearer '+self.server.capability):raise PanelError('console_access_required',401)
    def do_GET(self):
        try:
            self.boundary(self.path=='/api/state')
            if self.path in ASSETS:
                name,ctype=ASSETS[self.path];self.reply(200,(HERE/name).read_bytes(),ctype);return
            if self.path!='/api/state':raise PanelError('not_found',404)
            app=self.server.app
            if not app.lock.acquire(blocking=False):raise PanelError('operation_in_progress',409)
            try:self.reply(200,app.safe_json(app.snapshot()))
            finally:app.lock.release()
        except PanelError as exc:self.error(exc.code,exc.status)
        except (BrokenPipeError,ConnectionError,socket.timeout):pass
        except Exception:self.error('local_state_failed',500)
    def do_POST(self):
        try:
            self.boundary(True)
            if self.headers.get_all('Origin')!=[self.server.origin]:raise PanelError('invalid_origin',403)
            if self.headers.get_all('Content-Type')!=['application/json'] or self.headers.get('Transfer-Encoding'):raise PanelError('invalid_content_type',415)
            lengths=self.headers.get_all('Content-Length')
            if not lengths or len(lengths)!=1 or not re.fullmatch(r'[0-9]{1,6}',lengths[0]) or not 0<int(lengths[0])<=MAX_BODY:raise PanelError('body_size_limit',413)
            if not self.path.startswith('/api/') or self.path[5:] not in OPERATIONS:raise PanelError('not_found',404)
            raw=self.rfile.read(int(lengths[0]))
            if len(raw)!=int(lengths[0]):raise PanelError('incomplete_request',400)
            try:body=parse(raw)
            except Exception:raise PanelError('invalid_json',400) from None
            app=self.server.app
            if not app.lock.acquire(blocking=False):raise PanelError('operation_in_progress',409)
            try:
                self.reply(200,app.safe_json(app.dispatch(self.path[5:],body)))
                self.wfile.flush()
            finally:
                # Even a disconnected caller must not leave a completed quit
                # waiting forever. The UI treats a lost receipt as unconfirmed.
                if self.path=='/api/quit' and app.quit_requested:
                    app.shutdown_reply_pending=False
                app.lock.release()
        except PanelError as exc:self.error(exc.code,exc.status)
        except (BrokenPipeError,ConnectionError,socket.timeout):pass
        except Exception:self.error('local_operation_failed_check_state',500)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default=str(Path(os.environ['LOCALAPPDATA'])/'EH Client Data') if win else str(Path.home()/'.local/share/eh-subscription-console'))
    parser.add_argument('--endpoint',default=DEFAULT_ENDPOINT)
    parser.add_argument('--no-open',action='store_true',help='write private launch.json without opening the UI')
    parser.add_argument('--updater');parser.add_argument('--install-root');parser.add_argument('--update-notice')
    parser.add_argument('--chrome');parser.add_argument('--headless',action='store_true',help='start the owned task Chrome headless')
    args=parser.parse_args(argv);store=app=server=None;done=threading.Event();old={};exit_code=0
    try:
        if sys.platform not in ('darwin','linux','win32'):raise PanelError('supported_posix_platform_required')
        os.umask(0o077);store=Store(args.directory,args.endpoint)
        updates=UpdateBridge(args.updater,args.install_root,parse(args.update_notice) if args.update_notice else None)
        app=Console(store,chrome=args.chrome,headless=args.headless,updates=updates);server=LocalServer(app);server.timeout=.25
        if args.updater and args.install_root and not args.update_notice:updates.check()
        launch={'url':server.origin+'/#'+server.capability,'pid':os.getpid()};store.write('launch.json',launch)
        print(json.dumps({'status':'console_ready','origin':server.origin,'launch_file':str(store.root/'launch.json')}),flush=True)
        for sig in ((signal.SIGINT,signal.SIGTERM) if win else (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)):old[sig]=signal.signal(sig,lambda *_:done.set())
        if not args.no_open:webbrowser.open(launch['url'])
        while not done.is_set() and (not app.quit_requested or app.shutdown_reply_pending):server.handle_request()
    except PanelError as exc:print(json.dumps({'error':exc.code}));exit_code=2
    except Exception:print(json.dumps({'error':'console_failed'}));exit_code=2
    finally:
        if server:server.server_close()
        try:
            if app:
                cleanup=app.close()
                if cleanup.get('clean') is not True:
                    print(json.dumps({'error':'browser_cleanup_unconfirmed'}),flush=True);exit_code=2
        except Exception:
            print(json.dumps({'error':'console_cleanup_unconfirmed'}),flush=True);exit_code=2
        finally:
            if store:store.close()
            for sig,fn in old.items():signal.signal(sig,fn)
    return 20 if exit_code==0 and app and app.update_requested else exit_code

if __name__=='__main__':
    if sys.argv[1:]==['_remote']:remote_child()
    else:raise SystemExit(main())
