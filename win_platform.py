





import ctypes as c
from ctypes import wintypes as w
from contextlib import contextmanager
import json
import msvcrt
import os
from pathlib import Path
import stat
import time
import uuid

K=c.WinDLL('kernel32',use_last_error=True)
A=c.WinDLL('advapi32',use_last_error=True)
N=c.WinDLL('ntdll')
P=c.c_void_p
D=w.DWORD
H=w.HANDLE

def api(dll,name,args,result):
    f=getattr(dll,name);f.argtypes=args;f.restype=result;return f

close=api(K,'CloseHandle',[H],w.BOOL)
local_free=api(K,'LocalFree',[P],P)
create=api(K,'CreateFileW',[w.LPCWSTR,D,D,P,D,D,H],H)
get_security=api(A,'GetSecurityInfo',[H,D,D,c.POINTER(P),P,c.POINTER(P),P,c.POINTER(P)],D)
get_control=api(A,'GetSecurityDescriptorControl',[P,c.POINTER(w.WORD),c.POINTER(D)],w.BOOL)
sid_string=api(A,'ConvertSidToStringSidW',[P,c.POINTER(P)],w.BOOL)
sddl=api(A,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[w.LPCWSTR,D,c.POINTER(P),P],w.BOOL)
get_ace=api(A,'GetAce',[P,D,c.POINTER(P)],w.BOOL)
open_token=api(A,'OpenProcessToken',[H,D,c.POINTER(H)],w.BOOL)
token_info=api(A,'GetTokenInformation',[H,D,P,D,c.POINTER(D)],w.BOOL)
current_process=api(K,'GetCurrentProcess',[],H)
create_dir=api(K,'CreateDirectoryW',[w.LPCWSTR,P],w.BOOL)
move=api(K,'MoveFileExW',[w.LPCWSTR,w.LPCWSTR,D],w.BOOL)

class SA(c.Structure):
    _fields_=[('length',D),('descriptor',P),('inherit',w.BOOL)]
class INFO(c.Structure):
    _fields_=[('attrs',D),('creation',w.FILETIME),('access',w.FILETIME),('write',w.FILETIME),('volume',D),('sizehi',D),('sizelo',D),('links',D),('indexhi',D),('indexlo',D)]
file_info=api(K,'GetFileInformationByHandle',[H,c.POINTER(INFO)],w.BOOL)
class ACL(c.Structure):
    _fields_=[('revision',c.c_ubyte),('pad',c.c_ubyte),('size',w.WORD),('count',w.WORD),('pad2',w.WORD)]

def checked(ok):
    if not ok: raise c.WinError(c.get_last_error())
    return ok

def sid_text(ptr):
    out=P();checked(sid_string(ptr,c.byref(out)))
    try:return c.wstring_at(out)
    finally:local_free(out)

def owner_id():
    token=H();checked(open_token(current_process(),8,c.byref(token)))
    try:
        size=D();token_info(token,1,None,0,c.byref(size))
        buf=c.create_string_buffer(size.value);checked(token_info(token,1,buf,len(buf),c.byref(size)))
        return sid_text(c.cast(buf,c.POINTER(P))[0])
    finally:close(token)

@contextmanager
def security(directory=False):
    sid=owner_id();sd=P();flags='OICI' if directory else ''
    checked(sddl('O:'+sid+'D:P(A;'+flags+';FA;;;'+sid+')(A;'+flags+';FA;;;SY)',1,c.byref(sd),None))
    sa=SA(c.sizeof(SA),sd,False)
    try:yield c.byref(sa)
    finally:local_free(sd)

def validate_acl(handle, allow_admin_owner=False, protected=False):
    owner=P();dacl=P();sd=P()
    rc=get_security(handle,1,5,c.byref(owner),None,c.byref(dacl),None,c.byref(sd))
    if rc:raise OSError(rc,'private_acl_unreadable')
    try:
        sid=owner_id()
        if not owner or sid_text(owner) not in ({sid,'S-1-5-32-544'} if allow_admin_owner else {sid}) or not dacl:raise ValueError('private_acl_required')
        control=w.WORD();revision=D();checked(get_control(sd,c.byref(control),c.byref(revision)))
        if protected and not control.value&0x1000:raise ValueError('protected_directory_required')

        header=c.cast(dacl,c.POINTER(ACL)).contents
        if header.count != 2:raise ValueError('private_acl_required')
        seen=set()
        for i in range(header.count):
            ace=P();checked(get_ace(dacl,i,c.byref(ace)))
            kind=c.c_ubyte.from_address(ace.value).value
            flags=c.c_ubyte.from_address(ace.value+1).value
            mask=D.from_address(ace.value+4).value
            if kind!=0 or flags&8 or mask!=0x1f01ff:raise ValueError('private_acl_required')
            who=sid_text(ace.value+8)
            if who not in {sid,'S-1-5-18'} or who in seen:raise ValueError('private_acl_required')
            seen.add(who)
    finally:local_free(sd)

def path_check(path):
    p=Path(path).absolute()
    if not p.drive or str(p).startswith('\\\\') or ':' in str(p)[2:]:raise ValueError('local_ntfs_path_required')
    for item in (p,*p.parents):
        try:st=item.lstat()
        except FileNotFoundError:continue
        if getattr(st,'st_file_attributes',0)&0x400:raise ValueError('reparse_point_rejected')
    return p

@contextmanager
def opened(path,access=0x80000000,disposition=3,private=True,directory=False,share=7,allow_admin_owner=False):
    path=path_check(path)
    with security(directory) as sa:
        h=create(str(path),access|0x20000,share,sa,disposition,0x2200000,None)
    if h==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
    try:
        info=INFO();checked(file_info(h,c.byref(info)))
        if info.attrs&0x400 or bool(info.attrs&0x10)!=directory or (not directory and info.links!=1):raise ValueError('unsafe_file')
        if private:validate_acl(h,allow_admin_owner,protected=directory)
        yield h,info
    finally:close(h)

def private_dir(path,create=True,exclusive=False):
    path=path_check(path)
    if not path.exists():
        if create:
            if not path.parent.exists():private_dir(path.parent)
            with security(True) as sa:
                if not create_dir(str(path),sa):
                    if exclusive or c.get_last_error()!=183:raise c.WinError(c.get_last_error())
        else:raise FileNotFoundError(path)
    elif exclusive:raise FileExistsError(path)
    with opened(path,access=0,private=True,directory=True):pass
    return path

def fd_open(path,*,write=False,exclusive=False,create_file=False,private=True,share=7,allow_admin_owner=False):

    with opened(path,access=0xc0000000 if write else 0x80000000,
                disposition=1 if exclusive else 4 if create_file else 3,private=private,share=share,allow_admin_owner=allow_admin_owner) as (h,_):
        dup=H();duplicate=api(K,'DuplicateHandle',[H,H,H,c.POINTER(H),D,w.BOOL,D],w.BOOL)
        checked(duplicate(current_process(),h,current_process(),c.byref(dup),0,False,2))
        try:return msvcrt.open_osfhandle(dup.value,(os.O_RDWR if write else os.O_RDONLY)|os.O_BINARY)
        except BaseException:close(dup);raise

def read_file(path,limit,private=True,allow_admin_owner=False):
    with os.fdopen(fd_open(path,private=private,allow_admin_owner=allow_admin_owner),'rb') as f:
        if os.fstat(f.fileno()).st_size>limit:raise ValueError('file_too_large')
        raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('file_too_large')
    return raw

def stamp(path):
    with os.fdopen(fd_open(path),'rb') as f:
        st=os.fstat(f.fileno());return st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns

def atomic(path,raw):
    path=Path(path);private_dir(path.parent,create=False)
    tmp=path.with_name('.tmp-'+uuid.uuid4().hex)
    try:
        with os.fdopen(fd_open(tmp,write=True,exclusive=True),'wb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        path_check(path)
        if path.exists():
            with opened(path):pass
        checked(move(str(tmp),str(path),1|8))
    finally:
        if tmp.exists():tmp.unlink()

def lock_file(path):
    fd=fd_open(path,write=True,create_file=True,share=3)
    try:

        msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
        return fd
    except BaseException:os.close(fd);raise

def secure_json(path,limit=65536):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate_json_key')
            out[k]=v
        return out
    value=json.loads(read_file(path,limit),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid_json')))
    if not isinstance(value,dict):raise ValueError('json_object_required')
    return value



class ENTRY(c.Structure):
    _fields_=[('size',D),('usage',D),('pid',D),('heap',c.c_size_t),('module',D),('threads',D),('parent',D),('priority',w.LONG),('flags',D),('exe',w.WCHAR*260)]
snapshot=api(K,'CreateToolhelp32Snapshot',[D,D],H)
first=api(K,'Process32FirstW',[H,c.POINTER(ENTRY)],w.BOOL)
next_process=api(K,'Process32NextW',[H,c.POINTER(ENTRY)],w.BOOL)
open_process=api(K,'OpenProcess',[D,w.BOOL,D],H)
process_times=api(K,'GetProcessTimes',[H,c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME)],w.BOOL)
exit_code=api(K,'GetExitCodeProcess',[H,c.POINTER(D)],w.BOOL)
query_command=api(N,'NtQueryInformationProcess',[H,D,P,D,c.POINTER(D)],w.LONG)
terminate=api(K,'TerminateProcess',[H,w.UINT],w.BOOL)
class UNICODE(c.Structure):
    _fields_=[('length',w.USHORT),('maximum',w.USHORT),('buffer',P)]

def process_rows():
    h=snapshot(2,0)
    if h==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
    rows={};entry=ENTRY();entry.size=c.sizeof(entry)
    try:
        ok=first(h,c.byref(entry))
        while ok:
            rows[entry.pid]={'pid':entry.pid,'parent_pid':entry.parent,'exe':entry.exe}
            ok=next_process(h,c.byref(entry))
        if c.get_last_error()!=18:raise c.WinError(c.get_last_error())
        return rows
    finally:close(h)

def handle_identity(h,pid,parent):
    code=D();checked(exit_code(h,c.byref(code)))
    if code.value!=259:return None
    creation=w.FILETIME();a=w.FILETIME();b=w.FILETIME();d=w.FILETIME()
    checked(process_times(h,c.byref(creation),c.byref(a),c.byref(b),c.byref(d)))
    size=D();query_command(h,60,None,0,c.byref(size))
    if not 0<size.value<=131072:raise ValueError('process_command_unavailable')
    buf=c.create_string_buffer(size.value)
    if query_command(h,60,buf,len(buf),c.byref(size))<0:raise ValueError('process_command_unavailable')
    u=c.cast(buf,c.POINTER(UNICODE)).contents
    if u.length>len(buf) or not c.addressof(buf)<=u.buffer<=c.addressof(buf)+len(buf)-u.length:raise ValueError('process_command_invalid')
    command=c.wstring_at(u.buffer,u.length//2)
    return {'pid':pid,'parent_pid':parent,'started':str((creation.dwHighDateTime<<32)|creation.dwLowDateTime),'command':command}

def process_identity(pid):
    row=process_rows().get(pid)
    if row is None:return None
    h=open_process(0x1000,False,pid)
    if not h:
        if c.get_last_error()==87:return None
        raise c.WinError(c.get_last_error())
    try:return handle_identity(h,pid,row['parent_pid'])
    finally:close(h)

def descendant_ids(pid):
    rows=process_rows();found=[];seen={pid};pending=[pid]
    while pending:
        parent=pending.pop()
        for row in rows.values():
            if row['parent_pid']==parent and row['pid'] not in seen:
                found.append((row['pid'],parent));seen.add(row['pid']);pending.append(row['pid'])
        if len(found)>256:raise ValueError('browser_tree_limit')
    return found

def stop_owned(identities):
    handles=[]
    try:
        for identity in identities:
            h=open_process(0x1000|0x100000|1,False,identity['pid'])
            if not h:
                if c.get_last_error()==87:continue
                raise c.WinError(c.get_last_error())
            handles.append(h)
            current=handle_identity(h,identity['pid'],identity['parent_pid'])
            if current is None:continue
            if any(current[k]!=identity[k] for k in ('pid','started','command')):raise ValueError('process_identity_changed')


        for h in handles:
            code=D();checked(exit_code(h,c.byref(code)))
            if code.value==259:checked(terminate(h,0))
        wait=api(K,'WaitForSingleObject',[H,D],D)
        deadline=time.monotonic()+8
        for h in handles:
            if wait(h,max(0,int((deadline-time.monotonic())*1000)))!=0:raise ValueError('owned_processes_remain')
    finally:
        for h in handles:close(h)

def process_table(deadline):
    rows=process_rows();out={}
    for pid,row in rows.items():
        if time.monotonic()>=deadline:raise ValueError('process_observation_deadline')


        if row['exe'].lower() in ('chrome.exe','chromium.exe') or pid==os.getpid():
            item=process_identity(pid)
            if item is None:continue
        else:item=dict(pid=pid,parent_pid=row['parent_pid'],started='',command=row['exe'])
        item['stat']='R';out[pid]=item
    return out
