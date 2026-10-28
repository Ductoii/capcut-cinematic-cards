'use strict';
// MCP Apps host owns message routing and native confirmation. No private IPC.
window.CapCutHost=window.CAPCUT_MCP?(()=>{
  let sequence=0,connection=null,initialized=false,openResult=null;
  const pending=new Map();let readyResolve,readyReject;
  const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
  function request(method,params,timeout=30000){
    const id=++sequence;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Host chưa xác nhận yêu cầu. Trạng thái gửi chưa chắc chắn.'));},timeout);
      pending.set(id,{resolve,reject,timer});
      window.parent.postMessage({jsonrpc:'2.0',id,method,params},'*');
    });
  }
  function settle(){if(initialized&&openResult?.connection_id){connection=openResult.connection_id;readyResolve(connection);}}
  window.addEventListener('message',event=>{
    if(event.source!==window.parent||event.data?.jsonrpc!=='2.0')return;
    const m=event.data;
    if(m.id!==undefined&&pending.has(m.id)){
      const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);
      if(m.error)p.reject(new Error(m.error.message||'Host từ chối yêu cầu'));else p.resolve(m.result);
    }else if(m.method==='ui/notifications/tool-result'){
      openResult=m.params?.structuredContent;
      if(!openResult){try{openResult=JSON.parse(m.params?.content?.find(c=>c.type==='text')?.text||'{}');}catch{}}
      settle();
    }
  });
  async function call(name,args){
    const result=await request('tools/call',{name,arguments:args});
    if(result?.isError)throw new Error(result.content?.find(c=>c.type==='text')?.text||'Tool không hoàn tất');
    let data=result?.structuredContent;
    const text=result?.content?.find(c=>c.type==='text')?.text;
    if(text){try{data=JSON.parse(text);}catch{}}
    if(result?._meta?.media_base&&data&&typeof data==='object')data._media_base=result._meta.media_base;
    return data;
  }
  async function data(path){await ready;return call('capcut_workspace_data',{connection_id:connection,path});}
  async function action(value){await ready;return call('capcut_action',{connection_id:connection,action:value});}
  async function send(text,project_id,context={}){
    await ready;
    const id=crypto.randomUUID();const input={connection_id:connection,id,text,context};
    if(project_id)input.project_id=project_id;
    await call('capcut_request_create',input);
    const prompt=`[CapCut Harness request ${id}]\n${text}\n\nĐọc context bằng capcut_request_get với id ${id}; xác nhận đã nhận, xử lý trong chính chat này rồi cập nhật tiến độ/kết quả bằng capcut_request_update. Không thực hiện lại request đã hoàn tất.`;
    try{
      await request('ui/message',{role:'user',content:[{type:'text',text:prompt}]});
      await call('capcut_request_update',{id,state:'sent',from_ui:true});
    }catch(error){
      await call('capcut_request_update',{id,state:'delivery_uncertain',text:error.message,from_ui:true}).catch(()=>{});
      throw error;
    }
    return id;
  }
  request('ui/initialize',{appInfo:{name:'capcut-harness',version:'0.3.0'},appCapabilities:{},protocolVersion:'2026-01-26'})
    .then(()=>{initialized=true;window.parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*');settle();
      request('ui/request-display-mode',{mode:'fullscreen'}).catch(()=>{});})
    .catch(readyReject);
  return{ready,data,action,send,requests:()=>data('/api/requests')};
})():null;
