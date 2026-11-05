'use strict';
const $ = id => document.getElementById(id);
let capability=location.hash.slice(1)||sessionStorage.getItem('eh-console-access')||'';
if(capability){sessionStorage.setItem('eh-console-access',capability);history.replaceState(null,'',location.pathname);}
let termsRenderKey=null,appealHistory=null;
let state=null,busy=false,mode='login',view='overview',reauth=false,closing=false;
let supportReport=null,displayAccount=null,agentLink=null,agentScope=null;
let awaitingConnectionFeedback=false,displayedNotice=null;
const titles={overview:'准备好，让浏览器开始工作。',account:'购买、激活，再开始使用。',diagnostics:'让连接状态清楚可见。'};
const messages={terms_required:'请阅读并显式确认当前协议后再发起新的网页任务。',terms_update_required:'本机展示的协议与服务端版本或正文不同，请更新客户端后重新阅读。',terms_document_unavailable:'本机协议正文缺失或校验失败，请更新客户端。',invalid_request_reference:'请填写有效请求号：1–64 位字母、数字、点、下划线或短横线。',session_not_found:'未找到该任务。请核对原编号和当前账号；查询结果不代表可以重放操作。',request_not_found:'未找到该请求。请核对原编号；不要据此认定操作未执行或直接重放。',forbidden:'当前账号无权读取该记录。',unauthorized:'当前 Key 无效，请核对凭据。',invalid_remote_response:'服务返回格式异常，请稍后按原编号查询。',active_key_exists_rotate_required:'账号已有连接配置，请刷新状态后在连接诊断中核对。',active_key_changed_refresh_required:'有效 Key 已变化，请刷新核对后再操作。',subscription_disabled:'账号权益已停用，请联系运营核对；重复激活不会解除停用。',subscription_quota:'可用额度已用完，请查看账号额度。',subscription_not_started:'订阅尚未开始。',invalid_identifier:'名称仅支持 1–64 位英文字母、数字、点、下划线和短横线。',invalid_username:'用户名须为 1–64 个字符，支持中文和自定义名称；请勿使用控制字符或不可见字符。',console_access_required:'请从启动器重新打开控制台链接。',invalid_credentials:'用户名或密码不正确。',username_taken:'该用户名已注册，请登录。',account_login_required:'登录已过期，请重新登录。',login_required:'请先登录。',subscription_inactive:'账号尚未激活，请在购买与激活页输入激活码。',subscription_expired:'订阅已到期。',quota_exhausted:'可用额度已用完，请查看账号额度。',credentials_required:'请先点击准备本机使用，完成连接配置。',service_update_required:'服务端尚未升级到支持协议版本的版本，暂时无法注册；请联系运营更新服务。',previous_operation_requires_review:'上次请求尚未确认，请先核对远端状态。',response_unknown_check_remote_state:'响应未确认，操作可能已生效。请刷新并核对状态，不要重复提交。',disconnect_or_review_previous_connection:'请先断开浏览器；若上次异常退出，需要核实原浏览器的退出状态。',device_already_registered_rotate_if_credential_lost:'设备已经登记。若本机凭据丢失，请核对后换发设备凭据。',device_not_registered:'请先登记设备。',operation_in_progress:'上一个操作仍在处理中，请稍候。',api_key_limit:'Key 历史记录已达上限，请联系运营。',chrome_not_found:'未找到 Chrome，请先安装 Chrome。',private_directory_required:'数据目录必须仅供当前用户访问。',device_waiting_for_hub:'设备变更已保存，连接服务尚未确认应用；这还不代表设备已连接。',previous_connection_unconfirmed:'上次连接未确认退出。请到连接诊断点击“核实退出并恢复连接”，保留原数据目录。',browser_recovery_connection_running:'旧连接器仍在运行。请先点击断开浏览器，等待退出后再核实。',browser_recovery_directory_unverified:'原浏览器目录未通过核实，请保留原数据目录并联系支持人员检查。',browser_recovery_unconfirmed:'退出仍未确认。请先关闭旧 EH 工作浏览器并停止旧 EH 客户端连接，再点击核实；若仍失败，请保留原数据目录并提供诊断摘要。'};
function say(message,error=false){awaitingConnectionFeedback=false;$('feedback').hidden=false;$('feedback').className=error?'error':'';$('feedback').textContent=message;}
Object.assign(messages,{activation_code_invalid_or_unavailable:'激活码无效或不可使用，请核对完整内容或联系购买渠道。',activation_request_conflict:'该请求号已用于另一激活码，请先查询激活记录。',activation_rate_limited:'激活操作过于频繁，请稍后再试。',subscription_reactivation_review_required:'账号权益已停用，需要运营核对后恢复；购买或重复激活不能解除停用。',email_service_unavailable:'邮箱服务尚未启用，请联系运营。',email_queue_busy:'邮件队列繁忙，请稍后重新申请。',email_rate_limited:'申请或验证过于频繁，请15分钟后再试。',invalid_email:'请填写有效的邮箱地址。',email_proof_invalid_or_expired:'凭证无效、已过期或已使用，请检查完整内容或重新申请。',email_already_verified:'该账号已经验证邮箱，请使用更换邮箱。',email_not_verified:'请先验证首次绑定邮箱。',email_unchanged:'新邮箱须与当前绑定不同。',account_recovery_requires_quiet:'账号仍有业务任务，请先联系运营核对并关闭任务。',invalid_login:'用户名或密码不正确。'});
Object.assign(messages,{email_code_invalid_or_expired:'验证码不正确、已过期或已使用。请核对6位数字，或点击重新申请。',email_already_registered:'该邮箱已关联账号，请使用账号找回，或换一个邮箱。',email_in_use:'该邮箱已关联账号，请使用账号找回，或换一个邮箱。',email_unavailable:'该邮箱暂不可用于注册，请使用账号找回或换一个邮箱。',email_required:'注册时请填写邮箱，并在注册后完成邮箱验证。',email_not_pending:'当前没有待验证的注册邮箱，请刷新账号状态。',recovery_response_unknown_restart:'找回响应未确认，原操作可能已生效；不会自动重试。请尝试新密码登录，或点击重新申请验证码。',email_response_unknown_restart:'邮箱验证响应未确认，原操作可能已生效；不会自动重试。请刷新邮箱状态，未验证时可明确重新发送验证码。'});
Object.assign(messages,{appeal_request_conflict:'该申诉请求号已用于不同内容，请查询原申诉。',appeal_pending_exists:'已有待处理申诉，请查询处理状态。',appeal_not_eligible:'账号当前没有受限审核标记，请刷新状态；未激活或到期请按激活/续期流程处理。',appeal_state_changed:'账号或申诉状态已变化，请重新查询。',invalid_appeal_reason:'请填写1–1000字申诉说明，勿包含密码、验证码、Key、凭据或网页任务正文。',appeals_service_update_required:'当前控制台或服务端尚未支持站内申诉，请更新客户端并联系运营。现有状态查询和账号功能可继续使用。',appeal_rate_limited:'申诉提交过于频繁，请等待现有处理或稍后再试。',appeal_query_required:'请先按原请求号查到本人申诉，再解除本机核对提示。'});
Object.assign(messages,{subscription_plan_conflict:'当前账号的套餐类型不同，不能直接叠加。有效月套餐请到期后兑换永久额度；永久额度账号请使用永久激活码充值。',lifetime_frame_limit_exceeded:'永久总额度超过上限，请联系运营核对。'});
function errorMessage(e){return messages[e.code]||('操作未完成：'+(e.code||'connection_to_console_failed'));}
async function request(path,body,signal){let result;try{result=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+capability,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',credentials:'omit',redirect:'error',signal});}catch(_){throw {code:'response_unknown_check_remote_state'};}
let value;try{value=await result.json();}catch(_){throw {code:'response_unknown_check_remote_state'};}
if(!result.ok)throw {code:value.error||'request_failed'};return value;}
function choose(name){if(view!==name){$('main-content').scrollTop=0;window.scrollTo({top:0});}view=Object.hasOwn(titles,name)?name:'overview';name=view;document.querySelectorAll('[data-page]').forEach(x=>x.hidden=x.dataset.page!==name);document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===name));$('view-title').textContent=titles[name];}
function date(value){return typeof value==='number'&&Number.isFinite(value)&&value>0?new Date(value*1000).toLocaleString('zh-CN',{hour12:false}):'—';}
function renderUpdates(){const u=state.updates||{status:'installer_required'};
const source=u.status==='source_manual';
const message={source_manual:`源码运行，当前版本 ${state.version}。从 GitHub 手动更新：先退出客户端并停止 EH 工具连接，更新后重新启动。`,idle:'点击检查更新。',checking:'正在检查新版本…',available:`发现新版本 ${u.version}。请先断开专属浏览器，然后升级。`,up_to_date:`当前已是最新版本 ${state.version}。`,installed:`已成功升级到 ${state.version}。账号数据已保留。`,failed:'更新未完成，当前版本可继续使用。'+(u.error==='new_installer_required'?'请安装新的完整安装器。':`（${u.error||'update_failed'}）`),installer_required:'此安装器尚未接入在线更新，请安装新版完整安装器。'};
$('update-status').textContent=message[u.status]||'点击检查更新。';
$('update-check').hidden=source;$('update-check').disabled=source||busy||closing||u.status==='checking'||u.status==='installer_required';
$('update-apply').hidden=u.status!=='available';$('update-apply').disabled=source||busy||closing||Boolean(state.connection?.running)||state.connection?.clean===false||Boolean(state.pending);
}
function clearAgentLink(){agentLink=null;$('agent-one-line').value='';$('agent-line-preview').hidden=true;}
function currentAgentScope(){return JSON.stringify([state?.signed_in,state?.account,state?.version,state?.endpoint,state?.credentials?.key_id]);}
function clearAccountViews(){appealHistory=null;$('appeal-form').reset();$('appeal-history').replaceChildren();$('appeal-query-state').textContent='结果未确认时请用原请求号查回，不要重复提交。';for(const id of ['email-request-form','email-verify-form','email-change-request-form','email-change-confirm-form','recovery-request-form','recovery-code-form','recovery-reset-form','registration-email-verify-form','manual-request-form','manual-confirm-form'])$(id).reset();supportReport=null;$('activation-form').reset();$('activation-receipts-list').replaceChildren();$('activation-receipt-status').textContent='响应未确认时，先查询记录，不要重复提交。';$('support-preview').value='';$('support-preview').hidden=true;clearAgentLink();$('diagnostic-result').replaceChildren();}
const guideStages={terms:['阅读并确认协议','打开协议正文后，勾选并确认本机展示版本。仍可查询历史和断开连接。','查看协议','terms'],
login:['登录后继续','注册或登录你的账号。','登录','account'],
refresh:['先核对账号状态','读取最新权益和本机接入状态后，再继续。','刷新账号状态','refresh'],
review_operation:['上次操作还需核对','操作可能已经生效。请在连接诊断中核对，必要时联系运营；不要重复创建或换发。','查看诊断','diagnostics'],
review_connection:['先确认旧浏览器已退出','上次清理未确认。请在连接诊断点击“核实退出并恢复连接”，完成后即可重新连接。','查看诊断','diagnostics'],
review_device_connection:['设备连接被云端拒绝','本机专属 Chrome 已关闭。可能是设备凭据已失效，也可能有其他端正在连接。请先停止其他端，再重试连接；仍需在本机使用时，可到诊断页确认换发设备凭据。','核对设备连接','diagnostics'],
activation_review:['账号权益需要审核','请联系运营核对并恢复权益。购买激活码不能解除停用，已有激活记录仍可查询。','查看账号状态','account'],
activation:['购买并激活 Key','通过外部渠道或联系运营购买激活码，然后在账号页激活。','去激活','account'],
expired:['订阅已到期','购买激活码并激活续期，再继续使用。','激活续期','account'],
quota:['可用额度已用完','请核对账号余额。永久额度可兑换永久激活码充值；月套餐提前续期不会重置当期额度。','查看额度','account'],
create_key:['准备本机使用','权益已激活。客户端会为本机准备连接配置，然后可以连接浏览器。','准备本机使用','prepare'],
recover_key:['核对本机连接配置','本机连接配置与账号状态不匹配。请在连接诊断核对后修复；如需换发，旧配置将失效。','修复连接','diagnostics'],
enroll_device:['准备本机使用','连接配置已部分完成，继续登记本机设备。','继续准备','prepare'],
recover_device:['修复本机设备连接','本机设备连接需要核对。请在连接诊断中明确修复；换发时旧设备凭据将失效。','修复连接','diagnostics'],
enable_device:['设备已停用','在连接诊断核对设备后，明确启用。','修复连接','diagnostics'],
connect:['连接专属浏览器','本机准备完成。点击连接会检查 Chrome 并尝试连接，实际状态以连接结果为准。','连接浏览器','connect'],
connecting:['正在等待浏览器连接','请等待连接结果；失败时查看诊断，不会自动重放任务。','等待连接',null],
agent:['把 EH 接入你的 Agent','浏览器已连接。复制一句话给本机 Agent，让它读取资料、完成配置并检查 EH 状态。','复制一句话接入','agent_connect']};
function currentGuide(){return state?.pending?.operation==='redeem'?['核对激活结果','到购买与激活页查询激活记录。响应未确认不代表兑换失败，请勿重复提交。','查询激活结果','account']:(guideStages[state?.onboarding?.stage]||guideStages.refresh);}
function renderOnboarding(){const g=currentGuide();$('guide-title').textContent=g[0];$('guide-copy').textContent=g[1];$('guide-next').textContent=g[2];$('guide-next').disabled=busy||closing||!g[3];
}
function renderAppeals(){
const info=state.cloud?.appeals||{},supported=info.available===true,eligible=info.eligible===true||state.cloud?.activation_review_required===true,pending=state.pending?.operation==='appeal_create';
$('appeal-open').hidden=!eligible;$('appeal-open').disabled=busy;
$('appeal-state').textContent=eligible?'账号当前需要运营审核，可以提交一次申诉并查询处理结果。':'当前未显示受限审核标记。普通未激活或到期不属于封禁；仍可查询本人以往申诉。';
const hasPending=!!info.pending_id||(appealHistory?.appeals||[]).some(row=>row.status==='pending');
$('appeal-submit').disabled=busy||!supported||!eligible||!!state.pending||hasPending;
$('appeal-form').hidden=!supported||!eligible||hasPending;if(eligible&&!supported)$('appeal-state').textContent=messages.appeals_service_update_required;
$('appeals-refresh').disabled=busy||!supported||!state.signed_in;
$('appeal-release-unknown').hidden=!pending||state.pending.state!=='unknown';$('appeal-release-unknown').disabled=busy;
const uncertain=state.appeal_unconfirmed;$('appeal-unconfirmed-check').hidden=!uncertain;$('appeal-unconfirmed-check').disabled=busy||!supported;$('appeal-unconfirmed-note').hidden=!uncertain;if(uncertain)$('appeal-unconfirmed-note').textContent=`原申诉请求 ${uncertain.request_id} 的结果仍未知。解除本机提示不代表未提交；可继续查询原编号或通过联系邮箱人工核对。不会自动重发，新明确提交仍受单条待处理限制。`;
const email=appealHistory?.contact_email||info.contact_email,link=$('appeal-contact');link.hidden=!email;
if(email){link.href='mailto:'+encodeURIComponent(email);link.textContent='邮件联系运营：'+email;}else link.removeAttribute('href');
if(pending&&!appealHistory?.pending_confirmed)$('appeal-query-state').textContent=`申诉响应未确认，请求号 ${state.pending.request_id}。点击查询本人申诉 / 原请求；不会重发。`;
const list=$('appeal-history');list.replaceChildren();
for(const row of appealHistory?.appeals||[]){const item=document.createElement('li');const title=document.createElement('strong');title.textContent=({pending:'待处理',restored:'已恢复原权益',rejected:'未通过',closed:'已结束'})[row.status]||'待核对';item.append(title);for(const text of [`提交于 ${date(row.created_at)} · 请求号 ${row.request_id}`,'申诉说明：'+row.reason,'公开处理结果：'+(row.public_result||'等待运营处理')]){const p=document.createElement('p');p.textContent=text;item.append(p);}list.append(item);}
if(appealHistory&&!list.children.length){const item=document.createElement('li');item.textContent=pending?'尚未查到原请求，请稍后按原编号继续查询；不能据此认定未提交。':'暂无本人申诉记录。';list.append(item);}
}
function connectionRepair(){
 const stage=state?.onboarding?.stage,cloud=state?.cloud;
 if(!state?.signed_in||!cloud)return null;
 if(stage==='recover_key'){
  const keys=(cloud.keys||[]).filter(k=>!k.revoked);
  if(!keys.length)return {op:'key_create',body:{label:'local-client'},label:'重新准备连接配置',copy:'原连接配置不可用。确认后为本机创建新的连接配置。',confirm:'确认为当前账号重新准备本机连接配置？'};
  if(keys.length===1&&typeof keys[0].id==='string')return {op:'key_rotate',body:{key_id:keys[0].id,label:keys[0].label},label:'换发本机连接配置',copy:'本机缺少与账号匹配的连接配置。换发会使旧配置失效，请先确认原设备和宿主已停止使用。',confirm:'换发后旧 Key 立即失效，新配置保存到本机。确认继续？'};
  return null;
 }
 if(stage==='recover_device')return cloud.device?.registered===true?{op:'device_rotate',body:{},label:'换发本机设备凭据',copy:'本机设备凭据缺失或不匹配。换发会使旧设备凭据失效。',confirm:'确认原设备已停止使用，并换发设备凭据保存到本机？'}:{op:'device_enroll',body:{},label:'重新登记本机设备',copy:'账号尚未登记设备，请确认后为本机登记。',confirm:'确认为当前账号登记本机设备？'};
 if(stage==='review_device_connection'&&cloud.device?.registered===true)return {op:'device_rotate',body:{},label:'确认后换发设备凭据',copy:'云端拒绝了设备连接，本机专属 Chrome 已关闭。请先停止其他端的连接，再从概览重试；拒绝也可能由连接占用引起，不一定是凭据失效。若仍要在本机使用，可确认换发，旧端设备凭据将失效。',confirm:'确认继续在本机使用，并换发设备凭据？旧端设备凭据将立即失效，请先停止其他端的连接。换发后仍需手动连接验证，不会自动连接或重放网页动作。'};
 if(stage==='enable_device'&&cloud.device?.registered===true)return {op:'device_enable',body:{},label:'启用本机设备',copy:'设备已停用。请核对停用原因，再决定是否恢复连接。',confirm:'确认已核对停用原因，并重新启用本机设备？'};
 return null;
}
function connectionRepairBlocked(){const c=state?.connection||{};return busy||closing||!state?.signed_in||Boolean(state?.pending)||c.running===true||c.status==='starting'||c.status==='connected'||c.clean===false;}
function renderConnectionRepair(){const repair=connectionRepair();$('connection-repair-card').hidden=!repair;$('connection-repair-copy').textContent=repair?.copy||'';$('connection-repair').textContent=repair?.label||'核对后修复';$('connection-repair').disabled=!repair||connectionRepairBlocked();}
$('connection-repair').onclick=async()=>{const repair=connectionRepair();if(!repair||connectionRepairBlocked()||!confirm(repair.confirm))return;await act(repair.op,repair.body);};
function connectionFailureMessage(){const c=state?.connection||{};
 if(c.clean===false||c.status==='cleanup_unknown')return '浏览器退出尚未确认，请在连接诊断中核实清理状态后再继续。';
 if(c.clean===true&&c.first_error?.reason==='hub_rejected_connection'&&c.first_error?.phase==='hello')return guideStages.review_device_connection[1];
 return '浏览器连接未成功。请查看连接诊断中的错误详情；不会自动重连或重放网页动作。';
}
function updateConnectionFeedback(){if(!awaitingConnectionFeedback)return;const c=state?.connection||{};
 if(c.status==='connected')say('专属浏览器已连接，可以让 Agent 发起任务。');
 else if(['failed','stopped','cleanup_unknown'].includes(c.status))say('连接未成功。'+connectionFailureMessage(),true);
}
function render(){if(!state||closing)return;const scope=currentAgentScope();if(scope!==agentScope){clearAgentLink();agentScope=scope;}const identity=state.signed_in?state.account:null;if(identity!==displayAccount){clearAccountViews();displayAccount=identity;}renderUpdates();renderOnboarding();renderAppeals();const s=state,cloud=s.cloud,c=s.connection||{},running=c.running===true||c.status==='starting'||c.status==='connected',ready=s.credentials.api_ready&&s.credentials.device_ready;
$('auth').hidden=s.signed_in&&!reauth;$('recovery').hidden=s.signed_in&&!reauth;$('workspace').hidden=!s.signed_in||reauth;$('endpoint').textContent=s.endpoint;$('auth-endpoint').textContent=s.endpoint;$('version').textContent='EH / '+s.version;
$('username').textContent=s.username||'账号';
$('pending').hidden=!s.pending;if(s.pending)$('pending-text').textContent=s.pending.operation==='redeem'?`激活结果尚未确认（请求号 ${s.pending.request_id}）。请到“购买与激活”查询激活记录，核对后再继续；不要重复提交激活码。`:`操作 ${s.pending.operation} 尚未确认（${date(s.pending.started_at)}）。可先刷新账号状态，核对 Key / 设备是否已经生效。登记或换发的凭据若未保存，需明确换发；请勿直接重复原操作。`;
if(s.pending?.operation==='appeal_create')$('pending-text').textContent=`账号申诉结果尚未确认（请求号 ${s.pending.request_id}）。请在账号页查询原申诉；查询不会重发说明，查到后再解除核对提示。`;
const terms=s.terms_document||{},expected=cloud?.terms;
const termsKey=JSON.stringify([terms.version,terms.sha256,s.account]);if(termsKey!==termsRenderKey){termsRenderKey=termsKey;$('auth-form').elements.terms.checked=false;$('terms-accept-form').elements.accepted.checked=false;}
$('terms-registration-version').textContent=terms.version||'本机正文不可用';$('terms-renewal-version').textContent=terms.version||'本机正文不可用';
$('terms-renewal').hidden=!s.signed_in||!expected||expected.current===true;
const matching=terms.available===true&&expected?.version===terms.version&&expected?.sha256===terms.sha256;
$('terms-status').textContent=matching?'服务端需要你显式确认本机展示的协议版本。':'服务端与本机协议版本或正文不同，请先更新客户端后重新阅读；不能代为接受未展示版本。';
$('terms-accept-form').querySelector('button').disabled=busy||Boolean(s.pending)||!matching;
const status={offline:'未连接',starting:'正在连接',connected:'已连接',stopped:'已断开',failed:'连接失败',cleanup_unknown:'退出待核实'};
$('connection-badge').textContent=status[c.status]||'未连接';$('connection-badge').className='badge'+(c.status==='connected'?' online':'');
$('connection-title').textContent=c.status==='connected'?'浏览器已连接':running?'正在准备浏览器':s.onboarding?.stage==='review_device_connection'?'设备连接被云端拒绝':'连接你的本地浏览器';
$('connection-copy').textContent=c.status==='connected'?'本机浏览器已接入 EH。现在可以让你的 agent 发起任务。':c.status==='cleanup_unknown'||s.notice==='previous_connection_unconfirmed'?'上次退出未获确认。请到连接诊断点击“核实退出并恢复连接”，保留原数据目录。':s.onboarding?.stage==='review_device_connection'?guideStages.review_device_connection[1]:'激活后准备本机连接，再启动专属 Chrome。';
$('connect').disabled=busy||!ready||running||Boolean(s.pending)||c.clean===false;$('disconnect').disabled=busy||!running;$('agent-connect').disabled=busy||closing||!s.signed_in||!s.credentials.api_ready;
$('prepare').disabled=busy||!s.signed_in||running||Boolean(s.pending)||c.clean===false;$('activation-form').querySelector('button').disabled=busy||running||Boolean(s.pending)||cloud?.activation_review_required===true;$('activation-review-note').hidden=cloud?.activation_review_required!==true;$('activation-receipts').disabled=busy||!s.signed_in;$('refresh').disabled=busy||!s.signed_in;$('logout').disabled=busy||running;$('relogin').disabled=busy||running;
for(const id of ['check','diagnose'])$(id).disabled=busy||!ready;
$('recover_browser').hidden=c.clean!==false;$('recover_browser').disabled=busy||closing||c.clean!==false||c.running===true;
$('auth-submit').disabled=busy||Boolean(s.pending);$('recovery-entry').disabled=busy||Boolean(s.pending);
$('password-form').querySelector('button').disabled=busy||running||Boolean(s.pending);const recovery=cloud?.recovery;const blocked=busy||running||Boolean(s.pending);
$('email-status').textContent=recovery?.verified?`已验证：${recovery.email_masked||'邮箱已绑定'}${recovery.available?'':' · 邮件服务暂未启用'}`:recovery?.available?'尚未验证邮箱。':'邮箱服务暂未启用，或尚未刷新状态。';
const registrationPending=recovery?.pending_verification===true;
$('registration-email-verification').hidden=!registrationPending;
const emailFlow=s.email_verification||{stage:'request'};
$('registration-email-status').textContent=registrationPending?`待验证：${recovery.pending_email_masked||'注册邮箱'}。${emailFlow.stage==='code'?'验证码已申请，请查收邮件并填写。':'点击发送验证码，验证后才能找回账号。'}`:'';
$('registration-email-send').disabled=blocked||!recovery?.available;
$('registration-email-send').textContent=emailFlow.stage==='code'?'重新发送注册邮箱验证码':'发送注册邮箱验证码';
$('registration-email-verify-form').hidden=!registrationPending||emailFlow.stage!=='code';
$('registration-email-verify-form').querySelector('button').disabled=blocked;
for(const id of ['email-request-form','email-verify-form']){$(id).hidden=recovery?.verified===true||registrationPending;$(id).querySelector('button').disabled=blocked||(id==='email-request-form'&&!recovery?.available);}
for(const id of ['email-change-request-form','email-change-confirm-form']){$(id).hidden=true;$(id).querySelector('button').disabled=blocked||(id==='email-change-request-form'&&!recovery?.available);}
const resetFlow=s.account_recovery||{stage:'request'};
$('recovery-request-form').hidden=resetFlow.stage!=='request';
$('recovery-code-form').hidden=resetFlow.stage!=='code';
$('recovery-reset-form').hidden=resetFlow.stage!=='reset';
$('recovery-restart').hidden=resetFlow.stage==='request';$('recovery-restart').disabled=blocked;
$('recovery-username').textContent=resetFlow.stage==='reset'?resetFlow.username:'';
$('recovery-progress').textContent=resetFlow.stage==='code'?'验证码已申请。若邮箱已验证且可以找回，将收到6位数字；请检查收件箱及垃圾邮件。':resetFlow.stage==='reset'?'邮箱验证成功，请在5分钟内设置新密码。':'验证码与找回权限只保留在当前客户端内存中。';
for(const id of ['recovery-request-form','recovery-code-form','recovery-reset-form','manual-request-form','manual-confirm-form'])$(id).querySelector('button').disabled=blocked;
$('acknowledge').disabled=busy||(s.pending?.operation==='appeal_create'&&!appealHistory?.pending_confirmed);
const sub=cloud?.subscription||{},lifetime=sub.billing==='lifetime_frames'&&sub.metering==='frames'&&sub.expires_at===null&&sub.period_ends_at===null,active=sub.enabled===true&&(lifetime||(typeof sub.expires_at==='number'&&sub.expires_at>Date.now()/1000));
$('subscription-status').textContent=cloud?(cloud.activation_review_required?'需运营审核':active?'已开通':sub.enabled?'已到期':'未开通'):'尚未读取';$('remaining').textContent=cloud&&typeof sub.remaining==='number'?sub.remaining.toLocaleString():'—';$('expiry').textContent=lifetime?'永久有效':date(sub.expires_at);
const frameMeter=sub.metering==='frames';
$('remaining-label').textContent=lifetime?'剩余总额度':sub.billing==='calendar_month'?'本期剩余额度':'剩余额度';
$('billing-period').textContent=lifetime?`一次性总额度 ${sub.frame_limit?.toLocaleString()??'—'} 帧 · 已用 ${(sub.charged_frames??0).toLocaleString()} 帧 · 永久有效，用完即止，不按月重置。`:sub.billing==='calendar_month'?`本期（北京时间）：${new Date(sub.period_starts_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})} — ${new Date(sub.period_ends_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})} · 本月额度 ${(frameMeter?sub.frame_limit:sub.command_limit)?.toLocaleString()??'—'} ${frameMeter?'帧（成功新感知）':'次（旧命令口径）'} · 不结转；提前续费不刷新当月额度。`:'';
$('checked-at').textContent=s.cloud_checked_at?'最近核对：'+date(s.cloud_checked_at)+' · 权益以云端最新状态为准':'点击刷新账号状态以读取云端权益。';
const deviceReview=s.onboarding?.stage==='review_device_connection';
for(const [id,done] of [['step-account',active],['step-key',ready&&!deviceReview],['step-connect',c.status==='connected']])$(id).classList.toggle('done',done);
$('step-account-text').textContent=active?'订阅有效，查看账号页了解剩余额度':'购买激活码后，在账号页激活';$('step-key-text').textContent=deviceReview?'设备连接待核对，请到连接诊断查看':ready?'本机已准备好，连接浏览器后开始任务':'点击准备本机使用，完成连接配置';
renderConnectionRepair();
const errorDetail={...(c.first_error?{first_error:c.first_error}:{}),...(c.browser_cleanup_diagnostic?{browser_cleanup_diagnostic:c.browser_cleanup_diagnostic}:{})};
$('error-detail').textContent=Object.keys(errorDetail).length?JSON.stringify(errorDetail,null,2):c.status==='cleanup_unknown'?'浏览器退出未确认。请点击核实退出并恢复连接，保留原数据目录。':'暂无连接错误';
if(s.notice&&s.notice!==displayedNotice)say(messages[s.notice]||'状态需要核对：'+s.notice,true);displayedNotice=s.notice||null;choose(view);}
async function readState(){const next=await request('state');if(closing)return;state=next;render();updateConnectionFeedback();}
async function act(op,body={}){if(busy)return;const operationAccount=state?.signed_in?state.account:null;let activated=false;busy=true;if(op==='support_export'){supportReport=null;$('support-preview').value='';$('support-preview').hidden=true;}render();say('正在处理…');try{let value=await request(op,body);if(op==='redeem'){activated=true;value={...value,preparation:await request('prepare',{})};}if(op==='login'||op==='register')reauth=false,closing=false;await readState();if(['terms_accept','register','login','key_create','key_rotate','key_revoke','device_enroll','device_rotate','device_enable','device_revoke','acknowledge','email_verify','email_code_verify','appeals','appeal_create','redeem','prepare','activation_receipts'].includes(op)&&state.signed_in){await request('refresh',{});await readState();}
if(op==='redeem'){const p=value.preparation;say(p.status==='prepared'?'激活成功，本机已准备好。连接浏览器后即可按额度使用。':'激活已确认；'+(guideStages[p.stage]?.[1]||'本机准备尚未完成，请核对当前状态。'));choose(p.status==='prepared'?'overview':(guideStages[p.stage]?.[3]==='diagnostics'?'diagnostics':'account'));}
else if(op==='prepare'){say(value.status==='prepared'?'本机已准备好，可以连接浏览器。':guideStages[value.stage]?.[1]||'本机准备尚未完成，请核对当前状态。');if(value.status!=='prepared'&&guideStages[value.stage]?.[3]==='diagnostics')choose('diagnostics');}
else if(op==='activation_receipts'){$('activation-receipts-list').replaceChildren();for(const r of value.receipts){const li=document.createElement('li');li.textContent=`${date(r.redeemed_at)} · 套餐 ${r.plan_id} · ${r.billing==='lifetime_frames'?`永久有效 · 一次性总额 ${r.frames.toLocaleString()} 帧`:`${r.months} 个月 · 每月 ${r.frames.toLocaleString()} 帧`} · 请求号 ${r.request_id}`;$('activation-receipts-list').append(li);}$('activation-receipt-status').textContent=value.pending_confirmed?'已找到待核对请求的激活回执。确认记录后可解除核对提示，再准备本机使用。':value.receipts.length?'已读取激活记录。未匹配的请求仍需核对，不能据此认定未生效。':'暂无激活回执；请求仍可能在处理中，请稍后查询或联系运营。';say('已查询激活记录，未重复提交激活码。');}
else if(op==='check'||op==='diagnose'){const names={status:'检查结果',mode:'检查范围',api_config:'API 配置',device_config:'设备配置',chrome:'Chrome',api_health_ok:'API 认证',connector_tls_verified:'连接器 TLS',device_authentication:'设备认证',browser_started:'启动浏览器',error:'诊断代码'};const translations={checked:'通过',failed:'未通过',valid:'有效',found:'已找到',offline:'本机检查',online:'网络检查',not_tested:'未测试',true:'是',false:'否'};const dl=$('diagnostic-result');dl.replaceChildren();for(const [k,label] of Object.entries(names)){if(!(k in value))continue;const div=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=translations[String(value[k])]||String(value[k]);div.append(dt,dd);dl.append(div);}say(value.status==='checked'?(op==='check'?'本机检查完成。':'网络检查完成。')+'设备认证仍需实际连接验证。':'检查发现问题，请查看结果。',value.status!=='checked');}
else if(op==='support_export'){supportReport=value.report;$('support-preview').value=JSON.stringify(value.report,null,2);$('support-preview').hidden=false;say('诊断摘要已生成，请检查后下载。');}
else if(op==='appeals'||op==='appeal_create'){
if(operationAccount===null||!state.signed_in||state.account!==operationAccount){appealHistory=null;say('账号已变化，请重新查询本人申诉。',true);}
else{const history=op==='appeal_create'?await request('appeals',{}):value;
if(op==='appeal_create')await readState();
if(!state.signed_in||state.account!==operationAccount){appealHistory=null;say('账号已变化，请重新查询本人申诉。',true);}
else{appealHistory=history;
$('appeal-query-state').textContent=appealHistory.pending_confirmed?'已查到原请求的申诉记录。请核对状态，再解除本机核对提示。':'已读取本人申诉记录。提交不代表通过审核，也不会自动发送邮件。';
say(op==='appeal_create'?'申诉已提交，等待运营审核。不会自动解封或发送邮件。':'已查询本人申诉，未重发提交。');}}}
else if(op==='appeal_release_unknown')say('已解除本机提示并保留原请求号，申诉结果仍未知。请查询原编号或联系运营核对；没有重发申诉。');
else if(op==='logout'){authMode('login');say('已退出登录。');}
else if(op==='register'){choose('account');say('账号已创建。请发送注册邮箱验证码并完成验证；未验证的邮箱不能用于账号找回。');}
else if(op==='email_code_request')say('验证码申请已受理。请查看注册邮箱，只有收到邮件才能确认投递成功；15分钟内有效。');
else if(op==='email_code_verify')say('注册邮箱已验证，可以用于账号找回。');
else if(op==='recovery_code_request'){ $('recovery-details').open=true;say('申请已受理。若邮箱已验证且可找回，你会收到验证码；请检查收件箱和垃圾邮件。');}
else if(op==='recovery_code_verify')say('邮箱验证成功。请核对显示的用户名，再设置新密码。');
else if(op==='recovery_cancel')say('已清除本机找回步骤，请明确重新申请验证码；没有重试原请求。');
else if(op==='recovery_code_reset'){reauth=true;authMode('login');say('密码已重设，旧登录已注销。本机连接身份已清除，请使用新密码重新登录。');}
else if(op==='email_request')say('申请已受理，请查看邮箱。只有实际收到邮件才能确认投递成功；凭证15分钟内有效。');
else if(op==='email_change_request')say('已受理换绑申请。请分别查收原邮箱与新邮箱的凭证，必须同时提交。');
else if(op==='email_change_confirm'){reauth=true;authMode('login');say('邮箱已更换，所有旧登录已注销。请重新登录。');}
else if(op==='recovery_manual_request')say('已受理审核指定新邮箱的验证申请，请查收邮件。');
else if(op==='recovery_manual_confirm'){reauth=true;authMode('login');say('人工恢复完成。旧登录与Key已失效，订阅已暂停。请重新登录并联系运营核对设备和权益后启用，不会自动补额。');}
else if(op==='email_verify')say('邮箱已验证，可用于找回密码。');
else if(op==='recover_browser'){say('已确认旧浏览器和连接器退出。请点击连接浏览器，原网页登录资料已保留。');choose('overview');}
else if(op==='connect'){say('正在启动专属浏览器，请等待连接状态更新。');awaitingConnectionFeedback=true;updateConnectionFeedback();}
else if(op==='key_rotate'&&state.onboarding?.stage==='review_device_connection'){say('本机连接配置已换发。设备连接仍需核对：'+guideStages.review_device_connection[1],true);choose('diagnostics');}
else if(op==='device_rotate')say('设备凭据已换发，旧端设备凭据已失效。请手动连接浏览器验证；换发成功不代表设备已连接。');
else say(op==='disconnect'?'已请求停止，请核对连接状态。':op==='password'?'密码已修改，请重新登录。':'已完成。');
}catch(e){if(e.code==='account_login_required'){reauth=true;}try{await readState();}catch(_){}say((activated?'激活已确认，本机准备尚未完成。':'')+errorMessage(e),true);}
finally{busy=false;render();}}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>choose(b.dataset.view));
function authMode(next){mode=next;$('recovery-entry').hidden=next!=='login';$('login-tab').classList.toggle('selected',next==='login');$('register-tab').classList.toggle('selected',next==='register');$('confirmation-label').hidden=next!=='register';$('registration-email-label').hidden=next!=='register';$('auth-form').elements.email.required=next==='register';$('terms-label').hidden=next!=='register';$('auth-form').elements.terms.required=next==='register';$('auth-submit').textContent=next==='register'?'创建账号':'登录';$('auth-form').elements.confirmation.required=next==='register';$('auth-form').elements.password.autocomplete=next==='register'?'new-password':'current-password';}
$('login-tab').onclick=()=>authMode('login');$('register-tab').onclick=()=>authMode('register');
$('recovery-entry').onclick=()=>{if(busy||state?.pending)return;$('recovery-details').open=true;const stage=state?.account_recovery?.stage||'request';const form=$(stage==='reset'?'recovery-reset-form':stage==='code'?'recovery-code-form':'recovery-request-form');form.scrollIntoView({block:'center'});form.querySelector('input').focus({preventScroll:true});};
$('auth-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;if(mode==='register'&&f.elements.password.value!==f.elements.confirmation.value){say('两次密码输入不一致。',true);return;}if(mode==='register'&&!f.elements.terms.checked){say('请先阅读并同意《EH 订阅服务使用协议》。',true);return;}const body={username:f.elements.username.value,password:f.elements.password.value};if(Array.from(body.username.normalize('NFC').trim()).length>64){say(messages.invalid_username,true);return;}if(mode==='register'){body.email=f.elements.email.value.trim();body.terms_accepted=true;body.terms_version=state?.terms_document?.version;body.terms_sha256=state?.terms_document?.sha256;}f.elements.password.value='';f.elements.confirmation.value='';await act(mode,body);body.password='';};
$('password-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;if(f.elements.new_password.value!==f.elements.confirmation.value){say('两次新密码输入不一致。',true);return;}const body={old_password:f.elements.old_password.value,new_password:f.elements.new_password.value};f.reset();await act('password',body);body.old_password=body.new_password='';};
$('activation-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,body={code:f.elements.code.value.trim()};f.reset();try{await act('redeem',body);}finally{body.code='';}};
$('activation-receipts').onclick=()=>act('activation_receipts');
for(const op of ['refresh','prepare','connect','disconnect','check','diagnose','recover_browser'])$(op).onclick=()=>act(op);
$('logout').onclick=()=>act('logout');$('relogin').onclick=()=>{reauth=true;authMode('login');render();};
$('acknowledge').onclick=()=>{if(state?.pending&&confirm(state.pending.operation==='appeal_create'?'已按原请求号查到本人申诉并核对处理状态？此操作只解除本机核对提示，不会重新提交或自动解封。':state.pending.operation==='redeem'?'已经核对激活回执和账号权益？此操作仅解除本机核对提示，不重复兑换；仍不确定时请先查询或联系运营。':'已经核对远端 Key / 设备状态，并了解未保存的凭据需要撤销或换发？此操作仅解除本机阻止，不重试原请求。'))act('acknowledge',{operation_id:state.pending.id,reviewed:true});};
if(!capability){say('请运行客户端启动器，从它打开的页面进入控制台。',true);}else{readState().catch(e=>{if(!closing)say(errorMessage(e),true);});setInterval(()=>{if(!busy&&!closing)readState().catch(e=>{if(!closing&&e.code!=='operation_in_progress')say(errorMessage(e),true);});},2500);}

async function observeConsoleClosed(timeoutMs=10000,probeTimeoutMs=1000){
 const deadline=Date.now()+timeoutMs;
 while(Date.now()<deadline){
  if(navigator.onLine===false)return false;
  const controller=new AbortController();let timedOut=false;
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},Math.min(probeTimeoutMs,deadline-Date.now()));
  try{
   await fetch('/api/state',{method:'GET',headers:{Authorization:'Bearer '+capability},cache:'no-store',credentials:'omit',redirect:'error',signal:controller.signal});
  }catch(error){
   if(timedOut||controller.signal.aborted||error?.name!=='TypeError'||navigator.onLine===false)return false;
   return Date.now()<deadline;
  }finally{clearTimeout(timer);}
  const remaining=deadline-Date.now();
  if(remaining>0)await new Promise(resolve=>setTimeout(resolve,Math.min(250,remaining)));
 }
 return false;
}
async function quitClient(){
 if(busy||closing)return;
 if(!confirm('退出会断开专属浏览器连接，账号凭据会保留。确认退出？'))return;
 closing=true;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);
 say('正在退出并清理连接，请稍候…');
 const unknown='退出结果尚未确认。请检查启动终端；若客户端已停止，可关闭本页后重新启动，并到连接诊断核实退出状态。';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),65000);
 try{
  let receipt;
  try{receipt=await request('quit',{},controller.signal);}finally{clearTimeout(timer);}
  if(receipt?.status!=='shutdown_ready'||typeof receipt.connection_clean!=='boolean')throw {code:'invalid_shutdown_receipt'};
  say('连接清理已结束，正在确认控制台关闭…');
  if(!await observeConsoleClosed()){say(unknown,true);return;}
  if(receipt.connection_clean)say('客户端已退出，可以关闭此页面或重新启动。账号和网页登录资料已保留。');
  else say('控制台已关闭，但浏览器退出尚未确认。请重新启动客户端，在连接诊断中核实退出状态；原数据目录已保留。',true);
 }catch(_){say(unknown,true);}
 finally{clearTimeout(timer);busy=false;}
}
$('quit').onclick=quitClient;

$('update-check').onclick=()=>{if(state?.updates?.status==='source_manual')return;return act('update_check');};
$('update-apply').onclick=async()=>{if(busy||closing||state?.updates?.status==='source_manual')return;if(!confirm('下载并验证新版本，然后重启客户端？账号数据会保留。'))return;try{await request('update_apply',{});closing=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);say('正在验证和安装更新。完成后会打开新的客户端页面；若未自动打开，请重新启动 EH Client。');}catch(e){say(errorMessage(e),true);}};
messages.source_update_manual='源码版请从 GitHub 手动更新；先退出客户端并停止 EH 工具连接，更新后重新启动。';

Object.assign(messages,{agent_connect_account_required:'请先登录 EH 客户端。',agent_connect_credentials_required:'请先点击准备本机使用。',agent_connect_account_changed:'账号状态已变化，请核对后重新生成接入资料。',agent_connect_private_directory_required:'接入资料目录不满足本机私有存储要求，请检查客户端数据目录。',agent_connect_write_failed:'本机接入资料未能保存，请检查磁盘与数据目录后重试。',installer_metadata_incomplete:'安装器信息不完整，请使用完整 EH 客户端。',unsupported_agent_host:'当前客户端无法生成通用接入资料，请更新客户端。'});
async function connectAgent(){
 if(busy||closing||!state?.signed_in||!state.credentials.api_ready)return;
 const scope=currentAgentScope(),host='generic';busy=true;render();say('正在准备本机接入资料…');
 try{
  const value=agentLink||await request('agent_connect',{host});
  await readState();
  if(scope!==currentAgentScope()){clearAgentLink();say('账号或客户端已变化，请重新生成接入资料。',true);return;}
  if(value.host!==host||value.host_connection!=='not_verified'||value.contains_credentials!==false||typeof value.instruction!=='string'||!value.instruction||/[\r\n]/.test(value.instruction))throw {code:'invalid_remote_response'};
  agentLink=value;const field=$('agent-one-line');field.value=value.instruction;$('agent-line-preview').hidden=false;
  try{await navigator.clipboard.writeText(value.instruction);say('已复制一句话接入指令。发给本机 Agent 后，由它完成配置并验证工具；当前还未确认宿主已加载。');}
  catch(_){field.focus();field.select();say('本机资料已准备好。自动复制未完成，请复制已选中的一句话发给本机 Agent。');}
 }catch(e){clearAgentLink();say(errorMessage(e),true);}
 finally{busy=false;render();}
}
$('agent-connect').onclick=connectAgent;
$('guide-next').onclick=()=>{const next=currentGuide()[3];if(!next)return;if(['account','diagnostics'].includes(next)){choose(next);return;}if(next==='terms'){$('terms-renewal').scrollIntoView({block:'center'});return;}if(next==='agent_connect'){$('agent-connect').click();return;}act(next);};
$('support-export').onclick=()=>act('support_export');
$('support-download').onclick=()=>{if(!supportReport||busy)return;const url=URL.createObjectURL(new Blob([JSON.stringify(supportReport,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='eh-support-'+new Date(supportReport.generated_at*1000).toISOString().replaceAll(':','-')+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);say('已请求下载诊断摘要，文件不会自动发送。');};

for(const [id,op] of [['email-request-form','email_request'],['email-verify-form','email_verify'],['email-change-request-form','email_change_request'],['email-change-confirm-form','email_change_confirm'],['manual-request-form','recovery_manual_request'],['manual-confirm-form','recovery_manual_confirm']]){
 $(id).onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,body=Object.fromEntries(new FormData(f));
 if('confirmation' in body){if(body.confirmation!==body.new_password){say('两次新密码输入不一致。',true);return;}delete body.confirmation;}
 f.reset();try{await act(op,body);}finally{for(const k of Object.keys(body))body[k]='';}};
}

$('terms-accept-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;if(!f.elements.accepted.checked)return;await act('terms_accept',{terms_accepted:true,terms_version:state?.terms_document?.version,terms_sha256:state?.terms_document?.sha256});f.elements.accepted.checked=false;};

$('registration-email-send').onclick=()=>act('email_code_request');
$('registration-email-verify-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,body={code:f.elements.code.value.trim()};f.reset();try{await act('email_code_verify',body);}finally{body.code='';}};
$('recovery-request-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,body={email:f.elements.email.value.trim()};f.reset();try{await act('recovery_code_request',body);}finally{body.email='';}};
$('recovery-code-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,body={code:f.elements.code.value.trim()};f.reset();try{await act('recovery_code_verify',body);}finally{body.code='';}};
$('recovery-reset-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;if(f.elements.new_password.value!==f.elements.confirmation.value){say('两次新密码输入不一致。',true);return;}const body={new_password:f.elements.new_password.value};f.reset();try{await act('recovery_code_reset',body);}finally{body.new_password='';}};
$('recovery-restart').onclick=()=>act('recovery_cancel');

$('appeal-open').onclick=()=>{if(busy)return;$('appeals-section').open=true;$('appeals-section').scrollIntoView({block:'center'});if(state.cloud?.appeals?.available!==true){say(messages.appeals_service_update_required,true);return;}if(!$('appeal-form').hidden)$('appeal-form').elements.reason.focus({preventScroll:true});act('appeals');};
$('appeals-refresh').onclick=()=>act('appeals');
$('appeal-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,body={reason:form.elements.reason.value.trim()};if(!body.reason||Array.from(body.reason).length>1000){say(messages.invalid_appeal_reason,true);return;}form.reset();try{await act('appeal_create',body);}finally{body.reason='';}};

$('appeal-release-unknown').onclick=()=>{if(busy||state?.pending?.operation!=='appeal_create')return;if(confirm('已通过原请求号查询并与运营人工核对？原申诉结果仍可能已生效。此操作只解除本机提示并保留原编号，不判定未提交、不自动重发或解封；新明确提交仍受服务端单条待处理限制。'))act('appeal_release_unknown',{operation_id:state.pending.id,reviewed:true});};
$('appeal-unconfirmed-check').onclick=()=>state?.appeal_unconfirmed&&act('appeals',{request_id:state.appeal_unconfirmed.request_id});
