#!/usr/bin/env python3





from __future__ import annotations

import argparse
from contextlib import contextmanager
import getpass
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

if sys.platform == "win32":
    import importlib.util as _win_import
    _win_spec = _win_import.spec_from_file_location("eh_win_platform", Path(__file__).resolve().with_name("win_platform.py"))
    win = _win_import.module_from_spec(_win_spec); _win_spec.loader.exec_module(win)
else:
    win = None

HERE = Path(__file__).resolve().parent


def sibling(name):
    spec = importlib.util.spec_from_file_location('eh_account_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AccountError(Exception):
    pass


@contextmanager
def private_output(path):
    
    path = Path(path).expanduser().absolute()
    if path.resolve().is_relative_to(HERE) or path.parent.is_symlink():
        raise AccountError('credentials_must_be_outside_package')
    if win:
        win.private_dir(path.parent)
        fd = win.fd_open(path, write=True, exclusive=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as handle:
                def save(value):
                    json.dump(value, handle, ensure_ascii=False); handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
                yield save
        finally:
            if path.exists() and path.stat().st_size == 0: path.unlink()
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.parent.stat()
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise AccountError('credential_directory_requires_owned_mode_0700')
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    created = False
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        created = True
        with os.fdopen(fd, 'w', encoding='utf8') as handle:
            fd = None
            def save(value):
                json.dump(value, handle, ensure_ascii=False)
                handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
            yield save
        os.fsync(parent)
    finally:
        if fd is not None:
            os.close(fd)

        try:
            if created and os.stat(path.name, dir_fd=parent, follow_symlinks=False).st_size == 0:
                os.unlink(path.name, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def ask_password(prompt):
    if not sys.stdin.isatty():
        raise AccountError('interactive_terminal_required_for_password')
    return getpass.getpass(prompt)


def call(config, method, path, body=None):
    value, status = sibling('client').request(config, method, path, body)
    if status is None:
        raise AccountError('response_unknown_check_status_before_retry')
    if not 200 <= status < 300:
        code = value.get('error', 'request_failed')
        if not isinstance(code, str) or not re.fullmatch('[a-z0-9_]{1,100}', code):
            code = 'request_failed'
        raise AccountError(code)
    return value


def local_terms():
    
    try:
        page = (HERE / 'terms.html').read_text(encoding='utf8')
        version = re.search(r'<meta name="eh-terms-version" content="([0-9]{4}-[0-9]{2}-[0-9]{2}(?:\.[0-9]+)?)">', page)
        digest = re.search(r'<meta name="eh-terms-sha256" content="([a-f0-9]{64})">', page)
        body = re.search(r'<main class="terms">\n(.*?)\n</main>', page, re.S)
        if not version or not digest or not body or hashlib.sha256(body[1].encode()).hexdigest() != digest[1]:
            raise ValueError('invalid document')
        return {'version': version[1], 'sha256': digest[1]}
    except (OSError, UnicodeError, ValueError):
        raise AccountError('terms_document_unavailable') from None


def confirmed_terms(remote, version, digest):
    shown = local_terms()
    if shown != {'version': version, 'sha256': digest} or any(remote.get(k) != shown[k] for k in shown):
        raise AccountError('terms_update_required')
    return {'terms_version': shown['version'], 'terms_sha256': shown['sha256'], 'terms_accepted': True}


def show_terms():
    shown = local_terms()
    page = (HERE / 'terms.html').read_text(encoding='utf8')
    body = re.search(r'<main class="terms">\n(.*?)\n</main>', page, re.S)[1]
    print(html.unescape(re.sub(r'<[^>]+>', '\n', body)))
    print('协议版本：' + shown['version'] + '\n正文 SHA256：' + shown['sha256'])
    return shown


def safe(value):
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items() if k not in {'token', 'device_config', 'password', 'password_hash', 'salt', 'code', 'code_sha256', 'challenge', 'reset_token'}}
    if isinstance(value, list):
        return [safe(v) for v in value]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, help='existing private login file; never an EH API Key file')
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('register', 'login'):
        command = sub.add_parser(name)
        command.add_argument('--endpoint', required=True)
        command.add_argument('--username', required=True)
        command.add_argument('--output', type=Path, required=True)
    for name in ('me', 'keys', 'orders', 'device', 'activation-receipts', 'logout', 'password', 'device-revoke', 'device-enable'):
        sub.add_parser(name)
    sub.choices['register'].add_argument('--accept-terms', action='store_true',
        help='confirm the local agreement previously displayed by the terms command')
    sub.choices['register'].add_argument('--terms-version', help='version displayed by the terms command')
    sub.choices['register'].add_argument('--email', required=True, help='registration email; verify it in the local console before using account recovery')
    read = sub.add_parser('terms', help='read the bundled agreement and verify it matches the service')
    read.add_argument('--endpoint', required=True)
    accept = sub.add_parser('accept-terms', help='explicitly accept the displayed agreement using a login session')
    accept.add_argument('--accept-terms', action='store_true')
    accept.add_argument('--terms-version', required=True)
    redeem = sub.add_parser('redeem', help='redeem a purchased activation code, entered without echo')
    redeem.add_argument('--request-id', required=True, help='retain this identifier to check activation receipts after an unknown response')
    order = sub.add_parser('order')
    order.add_argument('--plan', required=True)
    order.add_argument('--request-id', required=True)
    key = sub.add_parser('key-create')
    key.add_argument('--label', required=True)
    key.add_argument('--output', type=Path, required=True)
    key = sub.add_parser('key-rotate')
    key.add_argument('--key-id', required=True, help='expected current Key ID, refresh before rotating')
    key.add_argument('--label', required=True)
    key.add_argument('--output', type=Path, required=True)
    key = sub.add_parser('key-revoke'); key.add_argument('--key-id', required=True)
    for name in ('device-enroll', 'device-rotate'):
        command = sub.add_parser(name); command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        setup = sibling('setup')
        if args.operation == 'terms':
            config = setup.api_config({'endpoint':args.endpoint, 'token':'anonymous-placeholder', 'timeout':15})
            shown = show_terms()
            confirmed_terms(call(config, 'GET', '/account/terms'), shown['version'], shown['sha256'])
            return 0
        if args.operation in {'register', 'login'}:
            config = setup.api_config({'endpoint': args.endpoint, 'token': 'anonymous-placeholder', 'timeout': 15})
            with private_output(args.output) as save:
                secret = ask_password('密码（12–128 字符，不回显）: ')
                if args.operation == 'register' and secret != ask_password('再次输入密码: '):
                    raise AccountError('password_confirmation_mismatch')
                payload = {'username': args.username, 'password': secret}
                if args.operation == 'register':
                    payload['email'] = args.email
                    if not args.accept_terms:
                        raise AccountError('terms_acceptance_required')
                    shown = local_terms()
                    payload.update(confirmed_terms(call(config, 'GET', '/account/terms'),
                                                   args.terms_version, shown['sha256']))
                value = call(config, 'POST', '/account/' + args.operation, payload)
                save(dict(config, token=value['token']))
                del secret
        else:
            if not args.session:
                raise AccountError('login_file_required')
            if args.session.expanduser().resolve().is_relative_to(HERE):
                raise AccountError('credentials_must_be_outside_package')
            config = setup.api_config(setup.secure_json(args.session))
            if not config['token'].startswith('ehs_'):
                raise AccountError('login_file_required_not_api_key')
            op = args.operation
            if op == 'accept-terms':
                if not args.accept_terms: raise AccountError('terms_acceptance_required')
                shown = local_terms()
                payload = confirmed_terms(call(config, 'GET', '/account/terms'), args.terms_version, shown['sha256'])
                value = call(config, 'POST', '/account/terms/accept', payload)
            elif op in {'me', 'keys', 'orders', 'device'}:
                value = call(config, 'GET', '/account/' + op)
            elif op == 'activation-receipts':
                value = call(config, 'GET', '/account/activation/receipts')
            elif op == 'redeem':
                if not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', args.request_id):
                    raise AccountError('invalid_identifier')
                code = ask_password('购买的激活码（不回显）: ').strip()
                try:
                    if not re.fullmatch(r'ehac_[A-Za-z0-9_-]{43}', code):
                        raise AccountError('activation_code_invalid_or_unavailable')
                    value = call(config, 'POST', '/account/activation/redeem', {'code': code, 'request_id': args.request_id})
                finally:
                    del code
            elif op in {'key-create', 'key-rotate'}:
                with private_output(args.output) as save:
                    body = {'label': args.label}
                    if op == 'key-rotate': body['key_id'] = args.key_id
                    value = call(config, 'POST', '/account/keys/' + op.split('-')[1], body)
                    save(dict(config, token=value['token']))
            elif op in {'device-enroll', 'device-rotate'}:
                with private_output(args.output) as save:
                    value = call(config, 'POST', '/account/device/' + op.split('-')[1], {})
                    device = sibling('connector').validate_config(value['device_config'])
                    save(device)
            elif op == 'order':
                value = call(config, 'POST', '/account/orders/create', {'request_id': args.request_id, 'plan_id': args.plan})
            elif op == 'key-revoke':
                value = call(config, 'POST', '/account/keys/revoke', {'key_id': args.key_id})
            elif op == 'password':
                old = ask_password('原密码: '); new = ask_password('新密码: ')
                if new != ask_password('再次输入新密码: '):
                    raise AccountError('password_confirmation_mismatch')
                value = call(config, 'POST', '/account/password', {'old_password': old, 'new_password': new})
                del old, new
            else:
                path = '/account/' + (op.replace('-', '/') if op.startswith('device-') else op)
                value = call(config, 'POST', path, {})
        print(json.dumps(safe(value), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, AccountError) else 'account_client_failed'
        print(json.dumps({'error': code, 'credentials_printed': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
