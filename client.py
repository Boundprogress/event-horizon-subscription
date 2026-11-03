#!/usr/bin/env python3











from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import sysconfig
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

if sys.platform == "win32":
    import importlib.util as _win_import
    _win_spec = _win_import.spec_from_file_location("eh_win_platform", Path(__file__).resolve().with_name("win_platform.py"))
    win = _win_import.module_from_spec(_win_spec); _win_spec.loader.exec_module(win)
else:
    win = None

MAX_CONFIG = 65_536
MAX_RESPONSE = 4_000_000
MAX_ARGS = 65_536
MAX_CANONICAL_ARGS = 32_768
FORBIDDEN_KEYS = {
    "path", "session_path", "state_path", "output_dir", "output_path", "cdp",
    "cdp_url", "cdp_http", "ws_url", "websocketdebuggerurl", "profile",
    "profile_path", "user_data_dir", "endpoint", "token", "authorization",
}
ARG_FIELDS = {
    "perceive": {"settle", "max_steps", "query", "pages", "details_per_page", "contract_mode", "collection_policies", "experience_refs", "meta_budget"},
    "act": {"kind", "target", "query", "fields", "decision", "submit"},
    "act-batch": {"actions", "decision"},
    "terminal": {"status", "conclusion", "bindings", "evidence", "basis",
                 "reason_code", "subgoal", "expected", "confidence", "model_response", "plan_patch", "strategy_patch", "experience_feedback", "experience_iteration"},
    "act-arm": {"plan"},
    "collect-sweep": {"collection", "seed", "decision", "max_segments", "max_seconds"},
}
ACT_KINDS = {
    "click", "fill", "key", "scroll", "back", "reload", "dismiss",
    "paginate", "switch_tab", "extract", "expand", "search",
    "select_option", "open_tab", "close_tab",
}


class ClientError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):

        return None


def read_config(path):
    
    path = Path(path)
    try:
        if win:
            raw = win.read_file(path, MAX_CONFIG)
        else:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                    raise ClientError("config must be a regular mode-0600 file")
                if hasattr(os, "getuid") and info.st_uid != os.getuid():
                    raise ClientError("config must be owned by the current user")
                raw = handle.read(MAX_CONFIG + 1)
    except ClientError:
        raise
    except OSError:
        raise ClientError("cannot securely read config") from None
    if len(raw) > MAX_CONFIG:
        raise ClientError("config exceeds size limit")
    try:
        config = json.loads(raw)
        endpoint, token = config["endpoint"], config["token"]
        timeout = float(config.get("timeout", 30))
    except (ValueError, KeyError, TypeError, OverflowError):
        raise ClientError("config requires endpoint, token and optional timeout") from None
    if not isinstance(endpoint, str) or not isinstance(token, str):
        raise ClientError("endpoint and token must be strings")
    if not token or len(token) > 4096 or any(not 33 <= ord(c) <= 126 for c in token):
        raise ClientError("invalid bearer token format")
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        parsed.port
    except ValueError:
        raise ClientError("invalid endpoint URL") from None
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ClientError("endpoint must be an HTTP(S) origin without credentials or query")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "::1", "localhost"):
        raise ClientError("plain HTTP is permitted only for a local tunnel endpoint")
    if not 0 < timeout <= 300:
        raise ClientError("timeout must be greater than zero and at most 300 seconds")
    return {"endpoint": endpoint.rstrip("/"), "token": token, "timeout": timeout}


def redact(value, token):
    if isinstance(value, str):
        return value.replace(token, "[REDACTED]") if token else value
    if isinstance(value, list):
        return [redact(item, token) for item in value]
    if isinstance(value, dict):
        return {redact(str(key), token): redact(item, token) for key, item in value.items()}
    return value


def read_response(response):
    raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ClientError("response exceeds size limit")
    encoding = response.headers.get("Content-Encoding", "").lower()
    if encoding == "gzip":
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(raw, MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE or not decoder.eof or decoder.unused_data:
            raise ClientError("invalid or oversized compressed response")
    elif encoding not in ("", "identity"):
        raise ClientError("unsupported response encoding")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ClientError("response must be a JSON object")
    return value


def live_response(value):
    
    if not isinstance(value, dict): return {}
    retired = {'historical_frame_id', 'local_replay', 'historical', 'cache_saved',
               'cache_error', 'local_cache_available', 'terminal_local_copy_saved',
               'terminal_copy_queries'}
    if any(key in value and value[key] is not False for key in ('local_replay', 'historical')):
        metadata = {key: value[key] for key in ('status', 'uncertain', 'session_id',
                    'request_id', 'content_retained', 'content_sha256',
                    'delivery_expires_at', 'lifecycle') if key in value}
        metadata.update(error='historical_content_not_supported', content_available=False,
                        available=False, needs_perceive=True)
        return metadata
    return {key: item for key, item in value.items() if key not in retired}


def request(config, method, path, body=None, *, opener=None):
    
    data = None if body is None else json.dumps(
        body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    headers = {"Authorization": "Bearer " + config["token"], "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        config["endpoint"] + path, data=data, method=method, headers=headers)
    opener = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect())
    try:
        try:
            response = opener.open(req, timeout=config["timeout"])
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.getcode()
            value = read_response(response)
        value = live_response(redact(value, config["token"]))
        return value, status
    except Exception as error:


        return {
            "status": "uncertain",
            "error": "transport_or_response_failure",
            "error_type": type(error).__name__,
        }, None




RESULT_QUERY_MIN_WINDOW_SECONDS = 1.0
PENDING_RESULT_STATES = frozenset({"pending", "queued", "running"})


def result_is_pending(current, code):
    
    return (isinstance(current, dict) and type(code) is int and 200 <= code < 300
            and isinstance(current.get("status"), str)
            and current["status"] in PENDING_RESULT_STATES
            and current.get("uncertain", False) is False
            and current.get("ok") is not False and not current.get("error"))


def wait_for_result(config, session_id, request_id, current, code, deadline,
                    *, request_fn=None, clock=None, sleep=None):
    
    request_fn = request_fn or request
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    polls = 0
    status_path = "/request?" + urllib.parse.urlencode({
        "session_id": session_id, "request_id": request_id})
    query_window = min(config["timeout"], RESULT_QUERY_MIN_WINDOW_SECONDS)
    while result_is_pending(current, code):
        remaining = deadline - clock()
        if remaining <= query_window:


            return current, code, polls, True



        advertised = current.get("result_wait_max_seconds")
        supports_wait = type(advertised) in (int, float) and advertised == 10
        if not supports_wait:
            sleep(min(1.0, remaining))
            remaining = deadline - clock()
            if remaining <= query_window:
                return current, code, polls, True
        timeout = min(config["timeout"], remaining)
        path = status_path
        if supports_wait:



            margin = min(1.0, timeout / 2)
            server_wait = min(10.0, timeout - margin)
            if server_wait < 0.001:
                sleep(min(1.0, remaining))
                remaining = deadline - clock()
                if remaining <= query_window:
                    return current, code, polls, True
                timeout = min(config["timeout"], remaining)
            else:
                path += "&wait_seconds=" + format(server_wait, ".6f").rstrip("0").rstrip(".")
        bounded = dict(config, timeout=timeout)
        current, code = request_fn(bounded, "GET", path, None)
        polls += 1
    return current, code, polls, False


def validate_identifier(value, name):
    pattern = r"[A-Za-z0-9_.-]{1,64}" if name == "request" else r"[A-Za-z0-9_.:-]{1,160}"
    if not re.fullmatch(pattern, value):
        raise ClientError(name + " has invalid characters or length")
    return value




TERMINAL_BASIS = frozenset({
    "task_constraint", "visible_text", "control_state", "navigation_state",
    "resource_reuse", "safety_recovery", "coverage", "transaction_result",
})


def validate_terminal_args(arguments):
    
    if not isinstance(arguments.get("status"), str) or arguments["status"] not in {"success", "partial", "failed"}:
        raise ClientError("invalid_terminal_status")
    if arguments.get("model_response", "") not in ("", "R1", "R2", "R3", "R4", "R5"):
        raise ClientError("invalid_model_response")
    for name, limit in (("conclusion", 600), ("model_response", 2),
                        ("subgoal", 100), ("expected", 140), ("reason_code", 80)):
        value = arguments.get(name, "")
        if not isinstance(value, str) or len(value) > limit or "\0" in value:
            raise ClientError("invalid_" + name)
        if name == "conclusion" or name in {"subgoal", "expected"} and name in arguments:
            if not value.strip():
                raise ClientError("invalid_" + name)
        if name in {"conclusion", "model_response"} and (value.lstrip().startswith("@") or value.strip() == "-"):
            raise ClientError("file_indirection_not_allowed")
    if not isinstance(arguments.get("confidence", "high"), str) or arguments.get("confidence", "high") not in {"low", "medium", "high"}:
        raise ClientError("invalid_terminal_confidence")
    for name in ADVANCED_PATCH_FIELDS & set(arguments):
        validate_advanced_patch(name, arguments[name])
    bindings = arguments.get("bindings", {})
    if not isinstance(bindings, dict):
        raise ClientError("bindings_must_be_object")
    if len(bindings) > 32:
        raise ClientError("terminal_bindings_limit_32")
    if arguments["status"] == "success" and not bindings:
        raise ClientError("success_requires_bindings")
    names = set()
    for name, ref in bindings.items():
        if (not isinstance(name, str) or not name.strip() or len(name) > 100
                or "=" in name or "\0" in name or not isinstance(ref, str)
                or not ref or len(ref) > 40 or re.search(r"[\s,\x00]", ref)):
            raise ClientError("invalid_binding")
        normalized = " ".join(name.split())
        if normalized in names:
            raise ClientError("duplicate_binding_name")
        names.add(normalized)

    def tokens(name, limit):
        values = arguments.get(name, [])
        if (not isinstance(values, list) or not all(isinstance(v, str) and
                0 < len(v) <= 200 and "\0" not in v for v in values)):
            raise ClientError(name + "_must_be_string_array")
        if len(values) > limit:
            raise ClientError("terminal_" + name + "_limit_" + str(limit))

        items = list(dict.fromkeys(x for v in values for x in re.split(r"[\s,]+", v.strip()) if x))
        if len(items) > limit:
            raise ClientError("terminal_" + name + "_limit_" + str(limit))
        if any(len(x) > 40 for x in items):
            raise ClientError("invalid_terminal_" + name)
        return items

    evidence = tokens("evidence", 12)
    if not evidence and len(set(bindings.values())) > 12:
        raise ClientError("terminal_evidence_required_for_over_12_bindings")
    basis = tokens("basis", 4)
    if any(x not in TERMINAL_BASIS for x in basis):
        raise ClientError("invalid_terminal_basis")


def validate_evidence_patch(patch):
    
    if not isinstance(patch, dict) or set(patch) - {"capture", "collection"} or "capture" not in patch:
        raise ClientError("invalid_evidence_patch")
    if "collection" in patch and (not isinstance(patch["collection"], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", patch["collection"])):
        raise ClientError("invalid_evidence_collection")
    capture = patch["capture"]
    if not isinstance(capture, list) or not 1 <= len(capture) <= 12:
        raise ClientError("evidence_capture_limit_1_12")
    seen = set()
    for item in capture:
        if (not isinstance(item, dict) or "id" not in item or set(item) - {"id", "name"}
                or not isinstance(item["id"], str) or len(item["id"]) > 40
                or not re.fullmatch(r"[NCUO][0-9]+(?:\.[0-9]+)*", item["id"])):
            raise ClientError("invalid_evidence_capture")
        if item["id"] in seen:
            raise ClientError("duplicate_evidence_capture")
        seen.add(item["id"])
        if "name" in item and (not isinstance(item["name"], str) or not item["name"].strip()
                or len(item["name"]) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in item["name"])):
            raise ClientError("invalid_evidence_name")


CURRENT_CONTRACT_ID = r"[NCUO][0-9]+(?:\.[0-9]+)*"
BATCH_KINDS = frozenset({"fill", "click", "key"})
BATCH_KEYS = frozenset({"Escape", "Enter", "Tab", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Backspace"})
DECISION_FIELDS = frozenset({"subgoal", "evidence", "basis", "expected", "confidence", "target", "action", "evidence_patch", "ledger", "memory_patch", "plan_patch", "strategy_patch", "experience_feedback", "experience_iteration"})
BATCH_DECISION_FIELDS = frozenset({"subgoal", "evidence", "basis", "expected", "confidence"})


def _bounded_text(value, maximum, code, *, empty=False, multiline=False):
    if (not isinstance(value, str) or len(value) > maximum or not empty and not value.strip()
            or any(ord(c) < 32 and not (multiline and c in "\r\n\t") or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ClientError(code)
    return value



def _ao(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}
def _at(maximum, pattern=None, *, empty=False):
    value={"type":"string","minLength":0 if empty else 1,"maxLength":maximum}
    if pattern:value["pattern"]=pattern
    return value
def _aa(item, maximum, minimum=0):
    return {"type":"array","items":item,"maxItems":maximum,"minItems":minimum}
def _ai(minimum, maximum):return {"type":"integer","minimum":minimum,"maximum":maximum}
def _an(minimum, maximum):return {"type":"number","minimum":minimum,"maximum":maximum}
def _ae(values):return {"type":"string","enum":list(values)}
ADVANCED_GROUPS=("meta","arm","collection","experience")
EXPERIENCE_REF_PATTERN=r"[a-z0-9][a-z0-9-]{0,79}/[a-z0-9][a-z0-9-]{0,79}"
ADVANCED_PATCH_FIELDS=frozenset({"plan_patch","strategy_patch","experience_feedback","experience_iteration"})
_CAPABILITIES=("tab_reuse","card_memory","static_receipt","candidate_overlay","delta","full","multi_action","audited_evidence")
_PLAN_PROPERTIES={"phase":_at(60),"goal":_at(120),"stop_when":_at(140),"action_budget":_ai(1,60),"perceive_budget":_ai(0,60),"reserve_actions":_ai(0,60),"reserve_perceives":_ai(0,60),"next_actions":_aa(_at(80),8,1),"reuse":_aa(_at(80),6)}
_STRATEGY_BODY=_ao({"capabilities":_aa(_ae(_CAPABILITIES),8,1),"phases":_aa(_at(180),8),"mandatory_boundaries":_aa(_at(140),8),"stop_conditions":_aa(_at(140),8)})
ADVANCED_SCHEMAS={
 "plan_patch":_ao({"op":_ae(("start","update","complete")),**_PLAN_PROPERTIES,"outcome":_at(120,empty=True)}),
 "strategy_patch":_ao({"op":_ae(("start","update","complete")),"trigger_event":_at(40,r"SE[0-9]{1,12}"),"phase":_at(60),"page_state":_at(100),"objective_mode":_at(80),"rationale":_at(180),"capabilities":_aa(_ae(_CAPABILITIES),8,1),"evidence_scope":_aa(_ae(("visible","visual","accessibility")),3,1),"experience_refs":_aa(_at(100,EXPERIENCE_REF_PATTERN),3),"outcome":_at(160,empty=True)},("trigger_event",)),
 "experience_feedback":_aa(_ao({"ref":_at(100,EXPERIENCE_REF_PATTERN),"used":{"type":"boolean"},"correctness":_an(0,1),"helpfulness":_an(0,1),"transferability":_an(0,1),"step_saving":_ai(-60,60),"note":_at(180,empty=True)},("ref",)),3,1),
 "experience_iteration":_ao({"family_id":_at(80,r"[a-z0-9][a-z0-9-]{0,79}"),"parent_version":_at(80,r"[a-z0-9][a-z0-9-]{0,79}"),"hypothesis":_at(220),"change_type":_ae(("strategy_refinement","capability_change","step_plan_change","scope_narrowing","scope_expansion","failure_recovery")),"changes":_aa(_at(180),8,1),"expected_delta":_ao({"actions":_ai(-200,200),"perceives":_ai(-200,200),"model_responses":_ai(-200,200),"wall_seconds":_an(-86400,86400),"cost":_an(-10000,10000)}),"applicability_delta":_ao({"requires":_aa(_at(140),8),"excludes":_aa(_at(140),8)}),"strategy":_STRATEGY_BODY,"step_plan":_ao(_PLAN_PROPERTIES)},("family_id","parent_version","hypothesis","change_type","changes")),
 "collection_policy":_ao({"id":_at(32,r"[a-z][a-z0-9_-]{0,31}"),"scope":_ae(("session",)),"prefix":_at(48,r"[A-Za-z_][A-Za-z0-9_.:-]{0,47}"),"width":_ai(1,6),"limit":_ai(1,96),"capture_scope":_ae(("any","whole_card","selected_node"))},("id","prefix","limit")),
 "meta_budget":_ao({"action_attempts":_ai(1,60),"perceive_attempts":_ai(1,200)}),
 "experience_query":_ao({"mode":_ae(("route","retrieve")),"contract":_ae(("v2","grid")),"page_state":_at(160),"limit":_ai(1,3),"objective":_at(4000),"task_pattern":_at(4000),"trigger_signature":_at(180)},("mode","contract")),
}

ADVANCED_SCHEMAS_PATCHES={name:ADVANCED_SCHEMAS[name] for name in sorted(ADVANCED_PATCH_FIELDS)}


def validate_advanced_schema(value, schema, depth=0):
    if depth>16:raise ClientError("advanced_arguments_too_deep")
    kind=schema.get("type")
    valid={"object":isinstance(value,dict),"array":isinstance(value,list),"string":isinstance(value,str),"integer":type(value)is int,"number":type(value)in(int,float) and math.isfinite(value),"boolean":type(value)is bool}
    if not valid.get(kind,False):raise ClientError("advanced_invalid_type")
    if "enum" in schema and value not in schema["enum"]:raise ClientError("advanced_invalid_enum")
    if kind=="object":
        if set(schema.get("required",()))-set(value):raise ClientError("advanced_missing_field")
        if len(value)>128:raise ClientError("advanced_too_many_fields")
        for key,child in value.items():
            if key not in schema["properties"]:raise ClientError("advanced_unknown_field")
            validate_advanced_schema(child,schema["properties"][key],depth+1)
    elif kind=="array":
        if not schema.get("minItems",0)<=len(value)<=schema.get("maxItems",128):raise ClientError("advanced_array_bounds")
        for child in value:validate_advanced_schema(child,schema["items"],depth+1)
    elif kind=="string":
        _bounded_text(value,schema.get("maxLength",65536),"advanced_invalid_text",empty=schema.get("minLength",0)==0)
        if len(value)<schema.get("minLength",0) or "pattern" in schema and not re.fullmatch(schema["pattern"],value):raise ClientError("advanced_invalid_identifier")
    elif kind in {"integer","number"}:
        if not schema.get("minimum",-math.inf)<=value<=schema.get("maximum",math.inf):raise ClientError("advanced_number_bounds")


def validate_advanced_patch(name,value):
    validate_advanced_schema(value,ADVANCED_SCHEMAS[name])
    if name=="plan_patch":
        op=value.get("op","start")
        required={"phase"} if op=="complete" else ({"phase","goal","stop_when","action_budget","perceive_budget","next_actions"} if op=="start" else set())
        if not required<=set(value):raise ClientError("plan_patch_missing_fields")
        allowed={"op","phase","outcome"} if op=="complete" else {"op",*_PLAN_PROPERTIES}
        if set(value)-allowed or op=="update" and not set(value)-{"op"}:raise ClientError("invalid_plan_patch_fields")
        for reserve,budget in (("reserve_actions","action_budget"),("reserve_perceives","perceive_budget")):
            if reserve in value and budget in value and value[reserve]>value[budget]:raise ClientError("plan_patch_reserve_exceeds_budget")
    elif name=="strategy_patch":
        op=value.get("op","start")
        required={"phase"} if op=="complete" else ({"phase","page_state","objective_mode","capabilities","rationale"} if op=="start" else set())
        if not required<=set(value):raise ClientError("strategy_patch_missing_fields")
        if op=="complete" and set(value)-{"op","trigger_event","phase","outcome"} or op=="update" and not set(value)-{"op","trigger_event"}:raise ClientError("invalid_strategy_patch_fields")
        if "evidence_scope" in value and "visible" not in value["evidence_scope"]:raise ClientError("strategy_requires_visible_evidence")
    elif name=="experience_feedback":
        refs=[item["ref"] for item in value]
        if len(set(refs))!=len(refs):raise ClientError("duplicate_experience_ref")


def validate_experience_query(arguments):
    validate_advanced_schema(arguments,ADVANCED_SCHEMAS["experience_query"])
    mode=arguments["mode"];required="objective" if mode=="route" else "task_pattern";forbidden="task_pattern" if mode=="route" else "objective"
    if required not in arguments or forbidden in arguments:raise ClientError("experience_query_mode_fields")
    validate_argument_size(arguments)
    return dict(arguments)


def validate_experience_args(arguments):
    return validate_experience_query(arguments)


def validate_arm_args(arguments):
    if not isinstance(arguments,dict) or set(arguments)!={"plan"}:raise ClientError("invalid_arm_arguments")
    plan=arguments["plan"]
    if not isinstance(plan,dict) or set(plan)-{"id","actions","checkpoint","coverage_mode"} or not {"id","actions","coverage_mode"}<=set(plan):raise ClientError("invalid_arm_plan_fields")
    if not isinstance(plan["id"],str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}",plan["id"]):raise ClientError("invalid_arm_plan_id")
    if not isinstance(plan.get("checkpoint","delta"),str) or plan.get("checkpoint","delta") not in {"delta","full"} or not isinstance(plan["coverage_mode"],str) or plan["coverage_mode"] not in {"operate","collect","navigate"}:raise ClientError("invalid_arm_plan_mode")
    actions=plan["actions"]
    if not isinstance(actions,list) or not 1<=len(actions)<=6:raise ClientError("arm_actions_limit_1_6")
    kinds=[]
    for index,item in enumerate(actions):
        if not isinstance(item,dict) or not isinstance(item.get("kind"),str) or item.get("kind") not in {"fill","click","key","scroll"}:raise ClientError("invalid_arm_action")
        kind=item["kind"];kinds.append(kind)
        allowed={"kind","decision"}|({"target","query","submit"} if kind=="fill" else {"target"} if kind=="click" else {"query"})
        required={"kind","decision"}|({"target","query"} if kind=="fill" else {"target"} if kind=="click" else {"query"})
        if set(item)-allowed or not required<=set(item):raise ClientError("invalid_arm_action_fields")
        validate_decision_args(item["decision"])
        if not BATCH_DECISION_FIELDS<=set(item["decision"]):raise ClientError("arm_decision_required")
        if kind in {"fill","click"} and (not isinstance(item["target"],str) or len(item["target"])>40 or not re.fullmatch(CURRENT_CONTRACT_ID,item["target"])):raise ClientError("invalid_arm_target")
        if kind=="fill":
            _bounded_text(item["query"],8000,"invalid_arm_query",multiline=True)
            if "submit" in item and type(item["submit"])is not bool:raise ClientError("invalid_arm_submit")
        elif kind=="key":
            if index!=len(actions)-1:raise ClientError("arm_key_must_be_last")
            _bounded_text(item["query"],100,"invalid_arm_keys")
            keys=[x.strip() for x in item["query"].split(",")]
            if not 1<=len(keys)<=6 or any(key not in BATCH_KEYS for key in keys):raise ClientError("invalid_arm_keys")
        elif kind=="scroll" and (not isinstance(item["query"],str) or item["query"] not in {"up","down","left","right","top"}):raise ClientError("invalid_arm_scroll")
    mode=plan["coverage_mode"]
    if mode=="operate" and (len(actions)<2 or "scroll" in kinds):raise ClientError("arm_operate_requires_2_6_no_scroll")
    if mode=="collect" and (kinds!=["scroll"] or actions[0]["query"]=="top"):raise ClientError("arm_collect_requires_one_nontop_scroll")
    if mode=="navigate" and any(kind!="scroll" for kind in kinds):raise ClientError("arm_navigate_requires_only_scroll")


def validate_sweep_args(arguments):
    schema=_ao({"collection":_at(32,r"[a-z][a-z0-9_-]{0,31}"),"seed":_at(40,CURRENT_CONTRACT_ID),"decision":_ao({}),"max_segments":_ai(1,24),"max_seconds":_an(.1,60)},("collection","seed","decision"))

    value={key:item for key,item in arguments.items() if key!="decision"} if isinstance(arguments,dict) else arguments
    slim=dict(schema,properties={key:item for key,item in schema["properties"].items() if key!="decision"},required=["collection","seed"])
    validate_advanced_schema(value,slim)
    if "decision" not in arguments:raise ClientError("sweep_decision_required")
    validate_decision_args(arguments["decision"])
    if not BATCH_DECISION_FIELDS<=set(arguments["decision"]):raise ClientError("sweep_decision_required")


def validate_memory_patch(patch):
    
    if not isinstance(patch, dict) or set(patch) - {"phase", "ops"}:
        raise ClientError("invalid_memory_patch")
    phase = patch.get("phase", "")
    _bounded_text(phase, 40, "invalid_memory_phase", empty=True)
    ops = patch.get("ops", [])
    if not isinstance(ops, list) or len(ops) > 4 or not phase.strip() and not ops:
        raise ClientError("memory_patch_requires_phase_or_1_4_ops")
    for item in ops:
        if not isinstance(item, dict) or not isinstance(item.get("op"), str) or item["op"] not in {"pin", "keep", "update", "drop"}:
            raise ClientError("invalid_memory_operation")
        op = item["op"]
        allowed = ({"op", "card", "purpose", "summary", "alias"} if op == "pin" else
                   {"op", "memory", "summary", "status"} if op == "update" else {"op", "memory"})
        required = ({"op", "card", "purpose", "summary"} if op == "pin" else
                    {"op", "memory", "summary"} if op == "update" else {"op", "memory"})
        if set(item) - allowed or not required <= set(item):
            raise ClientError("invalid_memory_operation_fields")
        if op == "pin":
            card = item["card"]
            if not isinstance(card, str) or len(card) > 40 or not re.fullmatch(CURRENT_CONTRACT_ID, card):
                raise ClientError("invalid_memory_card")
            if not isinstance(item["purpose"], str) or item["purpose"] not in {"function", "information", "candidate"}:
                raise ClientError("invalid_memory_purpose")
            if "alias" in item and (not isinstance(item["alias"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,15}", item["alias"])):
                raise ClientError("invalid_memory_alias")
        else:
            memory = item["memory"]
            if (not isinstance(memory, str) or len(memory) > 20
                    or not re.fullmatch(r"(?:M[0-9]+|[A-Za-z][A-Za-z0-9_-]{0,15})", memory)):
                raise ClientError("invalid_memory_reference")
        if "summary" in item:
            _bounded_text(item["summary"], 180, "invalid_memory_summary")
        if "status" in item and (not isinstance(item["status"], str) or item["status"] not in {"active", "complete"}):
            raise ClientError("invalid_memory_status")


def validate_decision_args(decision, *, batch=False):
    




    if not isinstance(decision, dict):
        raise ClientError("decision_required")
    allowed = BATCH_DECISION_FIELDS if batch else DECISION_FIELDS
    if set(decision) - allowed:
        raise ClientError("decision_field_not_allowed")
    if batch and not BATCH_DECISION_FIELDS <= set(decision):
        raise ClientError("batch_decision_required")
    for name, limit in (("subgoal", 100), ("expected", 140), ("target", 128), ("action", 128)):
        if name in decision:
            _bounded_text(decision[name], limit, "invalid_decision_" + name)
    if "confidence" in decision and (not isinstance(decision["confidence"], str) or decision["confidence"] not in {"low", "medium", "high"}):
        raise ClientError("invalid_decision_confidence")
    if "evidence" in decision:
        evidence = decision["evidence"]
        if (not isinstance(evidence, list) or not 1 <= len(evidence) <= 12
                or any(not isinstance(x, str) or not 1 <= len(x) <= 40 or re.search(r"[\s,\x00]", x) for x in evidence)):
            raise ClientError("invalid_decision_evidence")
    if "basis" in decision:
        basis = decision["basis"]
        if not isinstance(basis, list) or not 1 <= len(basis) <= 4 or any(not isinstance(x, str) or x not in TERMINAL_BASIS for x in basis):
            raise ClientError("invalid_decision_basis")
    if "evidence_patch" in decision:
        validate_evidence_patch(decision["evidence_patch"])
    if "ledger" in decision:
        _bounded_text(decision["ledger"], 700, "invalid_decision_ledger", multiline=True)
    for name in ADVANCED_PATCH_FIELDS & set(decision):
        validate_advanced_patch(name, decision[name])
    if "memory_patch" in decision:
        validate_memory_patch(decision["memory_patch"])
        pins = [item["card"] for item in decision["memory_patch"].get("ops", []) if item["op"] == "pin"]
        if any(card not in decision.get("evidence", []) for card in pins):
            raise ClientError("memory_pin_requires_decision_evidence")


def validate_perceive_args(arguments):
    if "contract_mode" in arguments and (not isinstance(arguments["contract_mode"],str) or arguments["contract_mode"] not in {"v2","grid"}):raise ClientError("invalid_contract_mode")
    if "meta_budget" in arguments:
        validate_advanced_schema(arguments["meta_budget"],ADVANCED_SCHEMAS["meta_budget"])
        if not arguments["meta_budget"]:raise ClientError("meta_budget_empty")
    if "experience_refs" in arguments:
        refs=arguments["experience_refs"];validate_advanced_schema(refs,_aa(_at(161,EXPERIENCE_REF_PATTERN),3))
        if len(set(refs))!=len(refs):raise ClientError("duplicate_experience_ref")
    if "collection_policies" in arguments:
        policies=arguments["collection_policies"];validate_advanced_schema(policies,_aa(ADVANCED_SCHEMAS["collection_policy"],8,1))
        if len({item["id"] for item in policies})!=len(policies):raise ClientError("duplicate_collection_policy")
        if sum(item["limit"] for item in policies)>96:raise ClientError("collection_limits_exceed_96")
    for name in ("max_steps", "pages", "details_per_page"):
        if name in arguments and (type(arguments[name]) is not int or not (1 if name == "max_steps" else 0) <= arguments[name] <= 200):
            raise ClientError("invalid_" + name)
    if "settle" in arguments and (type(arguments["settle"]) not in {int, float} or not math.isfinite(arguments["settle"]) or not 0 <= arguments["settle"] <= 30):
        raise ClientError("invalid_settle")
    if "query" in arguments:
        _bounded_text(arguments["query"], 8000, "invalid_query", empty=True, multiline=True)


def validate_batch_args(arguments):
    if not isinstance(arguments, dict) or set(arguments) != {"actions", "decision"}:
        raise ClientError("invalid_batch_arguments")
    validate_decision_args(arguments["decision"], batch=True)
    actions = arguments["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= 6:
        raise ClientError("batch_actions_limit_1_6")
    for item in actions:
        if not isinstance(item, dict) or not isinstance(item.get("kind"), str) or item["kind"] not in BATCH_KINDS:
            raise ClientError("invalid_batch_action_kind")
        kind = item["kind"]
        allowed = {"kind", "query"} if kind == "key" else {"kind", "target", "query", "submit"} if kind == "fill" else {"kind", "target"}
        required = {"kind", "query"} if kind == "key" else {"kind", "target", "query"} if kind == "fill" else {"kind", "target"}
        if set(item) - allowed or not required <= set(item):
            raise ClientError("invalid_batch_action_fields")
        if kind != "key" and (not isinstance(item["target"], str) or len(item["target"]) > 40 or not re.fullmatch(CURRENT_CONTRACT_ID, item["target"])):
            raise ClientError("invalid_batch_target")
        if kind == "fill":
            _bounded_text(item["query"], 8000, "invalid_batch_query", multiline=True)
            if "submit" in item and type(item["submit"]) is not bool:
                raise ClientError("invalid_batch_submit")
        elif kind == "key":
            _bounded_text(item["query"], 100, "invalid_batch_keys")
            keys = [x.strip() for x in item["query"].split(",")]
            if not 1 <= len(keys) <= 6 or any(x not in BATCH_KEYS for x in keys):
                raise ClientError("invalid_batch_keys")


def validate_view_args(kind, arguments):
    if kind not in {"evidence", "tabs", "result"} or not isinstance(arguments, dict):
        raise ClientError("invalid_view_arguments")
    allowed = {"session_id"} | ({"ids", "after", "limit"} if kind == "evidence" else {"after", "limit"} if kind == "tabs" else set())
    if set(arguments) - allowed or not isinstance(arguments.get("session_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", arguments["session_id"]):
        raise ClientError("invalid_view_arguments")
    result = dict(arguments)
    if kind == "result":
        return result
    limit = arguments.get("limit", 12 if kind == "evidence" else 20)
    if type(limit) is not int or not 1 <= limit <= (24 if kind == "evidence" else 50):
        raise ClientError("invalid_view_limit")
    prefix = "E" if kind == "evidence" else "T"
    if "after" in arguments and (not isinstance(arguments["after"], str) or not re.fullmatch(prefix + r"[0-9]{1,12}", arguments["after"])):
        raise ClientError("invalid_view_cursor")
    if "ids" in arguments:
        ids = arguments["ids"]
        if ("after" in arguments or not isinstance(ids, list) or not 1 <= len(ids) <= 12
                or any(not isinstance(x, str) or not re.fullmatch(r"E[0-9]{1,12}", x) for x in ids)
                or len(set(ids)) != len(ids) or len(ids) > limit):
            raise ClientError("invalid_view_ids")
    result["limit"] = limit
    return result


def validate_action_args(arguments):
    decision = arguments.get("decision")
    validate_decision_args(decision)
    if "query" in arguments:
        _bounded_text(arguments["query"], 8000, "invalid_query", empty=True, multiline=True)
    if "target" in arguments:
        _bounded_text(arguments["target"], 4096, "invalid_target")
    if "submit" in arguments and type(arguments["submit"]) is not bool:
        raise ClientError("submit_must_be_boolean")
    if "fields" in arguments:
        fields = arguments["fields"]
        if not isinstance(fields, dict) or len(fields) > 128:
            raise ClientError("invalid_fields")
        for key, value in fields.items():
            _bounded_text(key, 4096, "invalid_fields_key")
            _bounded_text(value, 8000, "invalid_fields_value", empty=True, multiline=True)
    kind = arguments.get("kind")
    if kind not in {"select_option", "open_tab", "close_tab"}:
        return
    if any(name in arguments for name in ("fields", "submit")):
        raise ClientError("action_argument_not_allowed")
    target, query = arguments.get("target"), arguments.get("query")
    if kind == "open_tab":
        if target is not None or not isinstance(query, str) or not 1 <= len(query) <= 8000:
            raise ClientError("invalid_open_tab_url")
        try:
            parsed = urllib.parse.urlsplit(query)
            port = parsed.port
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and not parsed.username and not parsed.password
                     and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in query))
        except ValueError:
            valid = False
        if not valid:
            raise ClientError("invalid_open_tab_url")
    elif kind == "close_tab":
        if not isinstance(target, str) or not re.fullmatch(r"T[0-9]{1,12}", target) or query is not None:
            raise ClientError("invalid_close_tab_target")
    elif (not isinstance(target, str) or len(target) > 40
            or not re.fullmatch(r"[NCUO][0-9]+(?:\.[0-9]+)*", target)
            or not isinstance(query, str) or not query.strip() or len(query) > 256
            or any(ord(c) < 32 or ord(c) == 127 for c in query)):
        raise ClientError("invalid_select_option")


def validate_argument_size(arguments):
    
    try:
        encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ClientError("invalid_json_arguments") from None
    if len(encoded) > MAX_CANONICAL_ARGS:
        raise ClientError("arguments_too_large")


def validate_args(raw, op=None):
    if len(raw.encode("utf-8")) > MAX_ARGS:
        raise ClientError("args exceeds size limit")
    try:
        value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, RecursionError):
        raise ClientError("args must be a JSON object") from None
    if not isinstance(value, dict):
        raise ClientError("args must be a JSON object")
    if op is not None:
        if op not in ARG_FIELDS:
            raise ClientError("invalid_operation")
        if set(value) - ARG_FIELDS[op]:
            raise ClientError("args contains fields not allowed for this operation")
        if op == "act":
            if value.get("kind") not in ACT_KINDS:
                raise ClientError("act requires an allowed kind")
            if not isinstance(value.get("decision"), dict):
                raise ClientError("act requires a decision JSON object")
        for key in ("decision", "fields", "bindings"):
            if key in value and not isinstance(value[key], dict):
                raise ClientError(key + " must be a JSON object")
        for key in ("evidence", "basis"):
            if key in value and (
                not isinstance(value[key], list)
                or not all(isinstance(item, str) for item in value[key])
            ):
                raise ClientError(key + " must be a string array")
        for key in ("conclusion", "model_response"):
            if key in value and (
                not isinstance(value[key], str)
                or value[key].startswith("@") or value[key] == "-"
            ):
                raise ClientError(key + " must be literal text without a file reference")
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise ClientError("args nesting exceeds limit")
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = re.sub(r"[-\s]", "_", str(key)).lower()
                if normalized in FORBIDDEN_KEYS or normalized.startswith("cdp_"):
                    raise ClientError("args contains a forbidden transport or local-path field")
                pending.append((child, depth + 1))
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    if op == "terminal":
        validate_terminal_args(value)
    elif op == "act":
        validate_action_args(value)
    elif op == "act-batch":
        validate_batch_args(value)
    elif op == "perceive":
        validate_perceive_args(value)
    elif op == "act-arm":
        validate_arm_args(value)
    elif op == "collect-sweep":
        validate_sweep_args(value)
    validate_argument_size(value)
    return value


def package_audit(directory=None):
    
    base = Path(directory or Path(__file__).parent).resolve()
    if not base.is_dir():
        raise ClientError("audit package directory does not exist")
    standard = set(getattr(sys, "stdlib_module_names", ()))
    files, imports, findings = [], [], []
    for index, path in enumerate(sorted(base.rglob("*"))):
        if index >= 10_000:
            raise ClientError("audit file count exceeds limit")
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(base).as_posix()
        info = path.lstat()
        files.append({"path": relative, "bytes": info.st_size,
                      "kind": "symlink" if path.is_symlink() else "file"})
        if path.is_symlink():
            findings.append({"file": relative, "reason": "symlink"})
            continue
        parts = set(path.relative_to(base).parts)
        if (parts & {"engine", "tools", "mods_semantic", "core"}
                or path.suffix.lower() in (
                    ".so", ".pyd", ".dylib", ".dll", ".pyc", ".zip", ".tar", ".gz", ".tgz", ".whl")
                or any(word in path.stem for word in ("geom_nest", "hit_select", "address_cards"))):
            findings.append({"file": relative, "reason": "possible_core_or_binary"})
        if path.suffix != ".py":
            continue
        if info.st_size > 2_000_000:
            findings.append({"file": relative, "reason": "oversized_python_source"})
            continue
        source = path.read_bytes()
        files[-1]["sha256"] = hashlib.sha256(source).hexdigest()
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            findings.append({"file": relative, "reason": "invalid_python"})
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [("." * node.level) + (node.module or "")]
            for name in names:
                is_standard = name.split(".", 1)[0] in standard
                imports.append({"file": relative, "line": node.lineno,
                                "module": name, "stdlib": is_standard})
                if not is_standard:
                    findings.append({"file": relative, "line": node.lineno,
                                     "reason": "non_stdlib_import", "module": name})
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else (
                    func.attr if isinstance(func, ast.Attribute) else "")
                if name in ("__import__", "import_module", "exec", "eval"):
                    findings.append({"file": relative, "line": node.lineno,
                                     "reason": "dynamic_code_or_import"})
    roots = {Path(sysconfig.get_path(key)).resolve() for key in ("stdlib", "platstdlib")}
    loaded = []
    for name, module in sorted(sys.modules.items()):
        location = getattr(module, "__file__", None)
        if not isinstance(location, str) or location.startswith("<"):
            continue
        resolved = Path(location).resolve()
        is_standard = any(resolved == root or root in resolved.parents for root in roots)
        if sys.platform == 'win32':


            runtime = Path(sys.base_prefix).resolve()
            stdzip = runtime / ('python%d%d.zip' % sys.version_info[:2])
            known = name.split('.', 1)[0] in standard or name in {'_frozen_importlib', '_frozen_importlib_external'}
            embedded = stdzip in resolved.parents or (resolved.parent == runtime and resolved.suffix.lower() == '.pyd')
            is_standard = is_standard or (known and embedded)
        is_standard = is_standard and not (
            {"site-packages", "dist-packages"} & set(resolved.parts))
        entry = {"module": name, "path": str(resolved), "stdlib": is_standard}
        loaded.append(entry)
        if not is_standard and resolved != Path(__file__).resolve():
            findings.append({"module": name, "reason": "external_loaded_module",
                             "path": str(resolved)})
    return {"status": "completed", "kind": "client_dependency_audit",
            "package": str(base), "files": files, "imports": imports,
            "loaded_modules": loaded, "findings": findings,
            "stdlib_only": not findings,
            "limitations": "Static imports and current loaded modules only; no proof against hidden code."}


def save_envelope(path, value, config_path=None):
    destination = Path(path).absolute()
    if destination.resolve() in {
        Path(__file__).resolve(),
        Path(config_path).resolve() if config_path else Path(__file__).resolve(),
    }:
        raise ClientError("output cannot overwrite config or client source")
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if win:
        win.private_dir(destination.parent, create=False)
        return win.atomic(destination, raw)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=".eh-reply-", dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def parser():

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS)
    common.add_argument("--out", default=argparse.SUPPRESS)
    common.add_argument("--json-only", action="store_true", default=argparse.SUPPRESS)
    root = argparse.ArgumentParser(description=__doc__, parents=[common])
    sub = root.add_subparsers(dest="operation", required=True)
    create = sub.add_parser("create", parents=[common])
    create.add_argument("--task", required=True)
    create.add_argument("--start-url", required=True)
    create.add_argument('--request', help='persist this creation id before submitting; query it after a lost response')
    lookup = sub.add_parser('session', parents=[common])
    selector = lookup.add_mutually_exclusive_group(required=True)
    selector.add_argument('--session')
    selector.add_argument('--request', help='original creation request id')
    listing = sub.add_parser('sessions', parents=[common])
    listing.add_argument('--limit', type=int, default=20)
    listing.add_argument('--after')
    closing = sub.add_parser('close', parents=[common])
    closing.add_argument('--session', required=True)
    command = sub.add_parser("command", parents=[common])
    command.add_argument("--session", required=True)
    command.add_argument("--request", required=True)
    command.add_argument("--frame")
    command.add_argument("--op", choices=("perceive", "act", "act-batch", "terminal", "act-arm", "collect-sweep"), required=True)
    command.add_argument("--args", default="{}")
    command.add_argument("--wait", nargs="?", const=180, type=float, default=0,
                         metavar="SECONDS", help="poll GET status for at most 180 seconds")
    status_parser = sub.add_parser("status", parents=[common])
    status_parser.add_argument("--session", required=True)
    status_parser.add_argument("--request", required=True)
    status_parser.add_argument("--wait", nargs="?", const=180, type=float, default=0,
                               metavar="SECONDS", help="poll GET status for at most 180 seconds")
    mcp = sub.add_parser("mcp", parents=[common], help="Run the local stdio MCP tool server")
    mcp.add_argument("--console-directory")
    mcp.add_argument("--directory", help="private submission journal directory for --config mode")
    mcp.add_argument("--expected-account", help="account binding from an EH-generated connection package")
    mcp.add_argument("--expected-endpoint", help="endpoint paired with --expected-account")
    export = sub.add_parser("mcp-config", parents=[common], help="Print credential-free MCP configuration")
    export.add_argument("--console-directory", required=True)
    export.add_argument("--updater")
    export.add_argument("--install-root")
    connect = sub.add_parser("agent-connect", parents=[common], help="Create private connection instructions and print one line for your local Agent")
    connect.add_argument("--console-directory", default=str(Path(os.environ['LOCALAPPDATA'])/'EH Client Data') if sys.platform=='win32' else str(Path.home()/'.local/share/eh-subscription-console'))
    connect.add_argument("--host", choices=("generic", "codex"), default="generic")
    connect.add_argument("--updater")
    connect.add_argument("--install-root")
    audit = sub.add_parser("audit", parents=[common])
    audit.add_argument("--package-dir")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.operation in {"mcp", "mcp-config", "agent-connect"}:
        import importlib.util
        spec = importlib.util.spec_from_file_location("eh_mcp_tools", Path(__file__).with_name("example_agent.py"))
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        try:
            if args.operation == "agent-connect":
                if hasattr(args, "config") or hasattr(args, "out"):
                    raise bridge.AgentError("agent_connect_console_directory_only")
                value = bridge.prepare_agent_link(args.console_directory, host=args.host, updater=args.updater, install_root=args.install_root)
                print(json.dumps(value, ensure_ascii=False) if getattr(args, "json_only", False) else value["instruction"])
                return 0
            if args.operation == "mcp-config":
                value = bridge.mcp_config(args.console_directory, updater=args.updater, install_root=args.install_root)
                print(json.dumps(value, ensure_ascii=False, indent=2))
                return 0
            if getattr(args, "out", None):
                raise bridge.AgentError("mcp_stdout_is_protocol_only")
            return bridge.serve_mcp(config_path=getattr(args, "config", None),
                                    console_directory=args.console_directory, directory=args.directory,
                                    expected_account=args.expected_account, expected_endpoint=args.expected_endpoint)
        except (BrokenPipeError, KeyboardInterrupt):
            return 0
        except Exception:
            print("EH connection instructions were not created; check the signed-in client and private directory."
                  if args.operation == "agent-connect" else
                  "EH MCP startup failed; check the private client configuration.", file=sys.stderr)
            return 2
    config_path, token = getattr(args, "config", None), ""
    try:
        if args.operation == "audit":
            envelope = package_audit(args.package_dir)
            exit_code = 0 if envelope["stdlib_only"] else 1
        else:
            if not config_path:
                raise ClientError("--config is required for API operations")
            config = read_config(config_path)
            token = config["token"]
            wait_seconds = getattr(args, "wait", 0)
            if not 0 <= wait_seconds <= 180:
                raise ClientError("--wait must be between 0 and 180 seconds")
            deadline = time.monotonic() + wait_seconds
            session = request_id = None
            if args.operation == "create":
                parsed = urllib.parse.urlsplit(args.start_url)
                if parsed.scheme not in ("http", "https") or not parsed.hostname:
                    raise ClientError("start-url must be HTTP(S)")
                if not args.task.strip() or len(args.task) > 32_000:
                    raise ClientError("task must contain 1 to 32000 characters")
                method, path = "POST", "/session"
                body = {"objective": args.task, "start_url": args.start_url}
                if args.request is not None:
                    request_id = validate_identifier(args.request, 'request')
                    body['request_id'] = request_id
            elif args.operation == 'session':
                if args.session is not None:
                    session = validate_identifier(args.session, 'session')
                    query = {'session_id': session}
                else:
                    request_id = validate_identifier(args.request, 'request')
                    query = {'request_id': request_id}
                method, path, body = 'GET', '/session?'+urllib.parse.urlencode(query), None
            elif args.operation == 'sessions':
                if not 1 <= args.limit <= 100:
                    raise ClientError('--limit must be between 1 and 100')
                query = {'limit': args.limit}
                if args.after is not None:
                    if not re.fullmatch('[0-9a-f]{32}', args.after):
                        raise ClientError('--after must be a session id')
                    query['after'] = args.after
                method, path, body = 'GET', '/sessions?'+urllib.parse.urlencode(query), None
            elif args.operation == 'close':
                session = validate_identifier(args.session, 'session')
                method, path, body = 'POST', '/session/close', {'session_id': session}
            else:
                session = validate_identifier(args.session, "session")
                request_id = validate_identifier(args.request, "request")
                if args.operation == "status":
                    method, path = "GET", "/request?" + urllib.parse.urlencode({
                        "session_id": session, "request_id": request_id})
                    body = None
                else:
                    frame = validate_identifier(args.frame, "frame") if args.frame else None
                    if args.op in ("act", "act-batch", "terminal", "act-arm", "collect-sweep") and frame is None:
                        raise ClientError("--frame is required for act and terminal")
                    method, path = "POST", "/command"
                    body = {"session_id": session, "request_id": request_id,
                            "frame_id": frame, "op": args.op,
                            "args": validate_args(args.args, args.op)}
            initial_config = config
            if wait_seconds:
                initial_config = dict(config, timeout=min(config["timeout"], wait_seconds))
            envelope, code = request(initial_config, method, path, body)
            polls, wait_expired = 0, False
            if wait_seconds and args.operation in ("command", "status"):
                envelope, code, polls, wait_expired = wait_for_result(
                    config, session, request_id, envelope, code, deadline)
            envelope["_client"] = {
                "operation": args.operation, "http_status": code,
                "submission_attempts": 1 if method == "POST" else 0,
                "status_queries": polls + (1 if method == "GET" else 0),
                "automatic_retry": False, "local_core_fallback": False,
            }
            if session is not None:
                envelope.setdefault('session_id', session)
            if request_id is not None:
                envelope.setdefault('create_request_id' if args.operation in ('create', 'session') else 'request_id', request_id)
            if code is None or envelope.get('status') == 'uncertain' or envelope.get('uncertain') is True:
                if args.operation in ('command', 'status'):
                    recovery = 'Run status with the original session and request IDs; do not resubmit a physical action.'
                elif args.operation == 'create':
                    recovery = ('Run session --request with the original creation ID; do not automatically create another session.'
                                if request_id else 'Session creation result is unknown. Do not automatically create another session.')
                elif args.operation == 'close':
                    recovery = 'Run session --session to query closure; previously dispatched actions are not cancelled.'
                else:
                    recovery = 'Query the same session or list again; this client does not retry automatically.'
                envelope['recovery'] = recovery
            if wait_expired:
                envelope["_client"]["wait_expired"] = True
                envelope["recovery"] = (
                    "Request remains pending; run status with the same session and request IDs.")
            exit_code = 0 if code is not None and 200 <= code < 300 else (3 if code is None else 2)
            if envelope.get("status") == "uncertain" or envelope.get("uncertain") is True:
                exit_code = 3
            if wait_expired:
                exit_code = 4
        envelope = redact(envelope, token)
        if getattr(args, "out", None):
            try:
                save_envelope(args.out, envelope, config_path)
            except (ClientError, OSError):


                envelope.setdefault("_client", {})["output_error"] = "cannot_save_response"
                exit_code = 2
        displayed = envelope
        if not getattr(args, "json_only", False):
            print("session_id={session} request_id={request} frame_id={frame} status={status}".format(
                session=envelope.get("session_id"), request=envelope.get("request_id"),
                frame=envelope.get("frame_id"), status=envelope.get("status")))
            decision = envelope.get("stdout") or envelope.get("decision")
            if isinstance(decision, str) and decision:
                print(decision.rstrip())


                displayed = dict(envelope)
                for key in ("stdout", "decision"):
                    if displayed.get(key) == decision:
                        del displayed[key]
                displayed["_client"] = dict(displayed.get("_client", {}),
                                             decision_printed_separately=True)
        print(json.dumps(displayed, ensure_ascii=False, indent=2))
        return exit_code
    except (ClientError, OSError, ValueError) as error:


        message = str(error) if isinstance(error, ClientError) else type(error).__name__
        print(json.dumps({"status": "client_error", "error": redact(message, token),
                          "automatic_retry": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
