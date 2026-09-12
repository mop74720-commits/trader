'use strict';
const $ = id => document.getElementById(id);
const money = value => new Intl.NumberFormat('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}).format(value);
const pct = value => (value * 100).toFixed(2) + '%';
const signed = value => (value >= 0 ? '+' : '−') + money(Math.abs(value));
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stamp = value => value ? value.replace('T',' ').replace('+00:00','') : '—';
let state = null;
let working = false;
let toastTimer;
const labels = {
  overview:['模拟账户','模拟账户与收益','查看合成行情下的持仓、收益与交易结果。'],
  decisions:['交易复盘','每笔模拟交易，为什么发生？','对照决策提议、独立审查和实际执行结果。'],
  factors:['策略研究','把灵感，交给数据检验。','候选信号经过样本外验证，仅进入观察或淘汰。'],
  system:['运行状态','持续运行，始终有界。','检查数据新鲜度、风险约束与完整事件记录。'],
  intelligence:['信息简报','市场发生了什么？','先读报道，再看关联资产、来源证据与待核实事项。']
};
function page(name) {
  if (!labels[name]) name='intelligence';
  document.querySelectorAll('.page').forEach(el => el.hidden = el.id !== name);
  document.querySelectorAll('.nav').forEach(el => {el.classList.toggle('active',el.dataset.page === name); el.setAttribute('aria-current',el.dataset.page === name ? 'page':'false');});
  ['page-label','page-title','page-description'].forEach((id,i) => $(id).textContent = labels[name][i]);
  document.querySelector('.toolbar').hidden = name === 'intelligence';
  document.querySelector('.mode-badge').hidden = name === 'intelligence';
  $('sim-time').hidden = name === 'intelligence';
  document.querySelector('.eyebrow').textContent = name === 'intelligence' ? '公开来源 · 持续更新' : 'OBSERVE. REASON. EXECUTE.';
  history.replaceState(null,'','#'+name);
  window.scrollTo(0,0);
}
document.querySelectorAll('[data-page]').forEach(el=>el.addEventListener('click',()=>page(el.dataset.page)));
document.querySelectorAll('[data-goto]').forEach(el=>el.addEventListener('click',()=>page(el.dataset.goto)));
window.addEventListener('hashchange',()=>page(location.hash.slice(1)));
page(location.hash.slice(1));
window.addEventListener('load',()=>window.scrollTo(0,0));
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,4500); }
async function command(action, message) {
  if (working) return;
  working=true; controls();
  try {
    const response=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const result=await response.json();
    if(!response.ok) throw new Error(result.error || '操作失败');
    toast(message); await refresh();
  } catch(error) {toast(error.message);} finally {working=false;controls();}
}
$('run-button').addEventListener('click',()=>command(state?.running?'pause':'start',state?.running?'自动模拟已暂停':'自动模拟已启动'));
$('step-button').addEventListener('click',()=>command('step','已推进 1 小时，认知轮将在后台运行'));
$('research-button').addEventListener('click',()=>command('research','研究已完成，结果见因子研究页'));
$('cognize-button').addEventListener('click',()=>command('cognize','认知任务已请求；同一快照不会重复下单'));
$('flatten-button').addEventListener('click',()=>{if(confirm('停止实验、平掉所有模拟仓位并锁定账户？后续实验需要新数据库。'))command('flatten','模拟仓位已清空，账户已锁定');});
function controls(){
  ['run-button','step-button','research-button','cognize-button','flatten-button'].forEach(id=>$(id).disabled=working||!state);
  if(state){$('run-button').disabled=working||state.halted;$('step-button').disabled=working||state.running;$('cognize-button').disabled=working||state.busy;$('flatten-button').disabled=working||state.halted;}
}
function metric(id, value, tone){$(id).textContent=value;$(id).classList.remove('positive','negative');if(tone)$(id).classList.add(tone);}
function chart(points){
  if(!points.length) return;
  const W=800,H=260,left=14,right=83,top=18,bottom=25;
  const values=points.map(p=>p.equity);let lo=Math.min(...values),hi=Math.max(...values);let pad=Math.max((hi-lo)*.2,1);lo-=pad;hi+=pad;
  const x=i=>left+i/Math.max(points.length-1,1)*(W-left-right);
  const y=v=>top+(hi-v)/(hi-lo)*(H-top-bottom);
  const line=points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p.equity).toFixed(1)).join(' ');
  let html='<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#b6ef6c" stop-opacity=".15"/><stop offset="100%" stop-color="#b6ef6c" stop-opacity="0"/></linearGradient></defs>';
  for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4,yy=y(v);html+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" stroke="#2b3337" stroke-dasharray="3 6"/><text x="${W-right+12}" y="${yy+4}">${money(v)}</text>`;}
  html+=`<path d="${line} L${x(points.length-1)},${H-bottom} L${left},${H-bottom} Z" fill="url(#fill)"/><path d="${line}" fill="none" stroke="#b6ef6c" stroke-width="2" stroke-linejoin="round"/><circle cx="${x(points.length-1)}" cy="${y(values.at(-1))}" r="4" fill="#b6ef6c"/>`;
  $('equity-chart').innerHTML=html;
  $('chart-start').textContent=stamp(points[0].time)+' UTC';$('chart-end').textContent=stamp(points.at(-1).time)+' UTC';
}
function preview(round){
  if(!round)return '<div class="empty"><strong>等待首轮认知</strong>推进行情或运行认知轮以生成记录</div>';
  return `<div class="decision-preview"><div class="decision-meta"><span>ROUND ${round.id} · ${esc(round.proposal.regime.toUpperCase())}</span><span class="${round.review.verdict==='approve'?'positive':'negative'}">${round.review.verdict==='approve'?'APPROVED':'VETOED'}</span></div><p>${esc(round.proposal.thesis)}</p><div class="review">${esc(round.review.reason)}</div></div>`;
}
function render(s){
  const a=s.account,h=s.health;
  $('sim-time').textContent=stamp(s.time)+' UTC';
  $('run-state').textContent=s.halted?'账户已锁定':s.running?'自动模拟运行中':'模拟已暂停';
  $('run-dot').style.background=s.halted?'var(--red)':s.running?'var(--green)':'#7b878e';
  $('intel-decision-mode').textContent=s.provider==='rules'?'模拟决策：规则模式，新闻不参与买卖信号。':'模拟决策：模型模式，情报作为输入，尚未验证判断效果。';
  $('provider-label').textContent=s.provider==='rules'?'规则决策 · 无模型费用':'模型 API 决策';
  $('run-button').textContent=s.running?'暂停模拟 Ⅱ':'启动模拟 ▶';
  $('error-banner').hidden=!h.last_error;$('error-banner').textContent=h.last_error||'';
  metric('equity',money(a.equity));metric('principal',money(a.principal));metric('pnl',signed(a.pnl),a.pnl>=0?'positive':'negative');
  metric('total-return',(a.return>=0?'+':'')+pct(a.return));metric('drawdown',pct(-a.drawdown));metric('max-dd',pct(-a.max_drawdown));metric('exposure',pct(a.exposure));
  chart(s.curve);
  ['planner','critic','researcher'].forEach(role=>$(role+'-model').textContent=s.models[role]);
  $('risk-ticks').textContent=h.risk_ticks.toLocaleString();$('round-count').textContent=h.round_count;
  $('market-rows').innerHTML=Object.entries(s.market).map(([symbol,m])=>`<tr><td class="asset">${esc(symbol)}<small>/ USDC</small></td><td>${money(m.price)}</td><td class="${m.momentum>=0?'positive':'negative'}">${m.momentum>=0?'+':''}${pct(m.momentum)}</td><td>${pct(m.volatility)}</td><td><div class="efficiency"><progress value="${m.efficiency}" max="1"></progress>${m.efficiency.toFixed(3)}</div></td><td>${m.zscore.toFixed(2)} σ</td><td><span class="regime ${m.efficiency>.22?'':'range'}">${m.efficiency>.22?'趋势':'震荡'}</span></td></tr>`).join('');
  $('position-count').textContent=s.positions.length;$('stop-coverage').textContent=h.stop_coverage===null?'当前无仓位':'止损覆盖 '+pct(h.stop_coverage);
  $('positions').innerHTML=s.positions.length?s.positions.map(p=>`<div class="position"><div><b>${esc(p.symbol)} <span class="positive">LONG</span></b><p>${p.quantity.toFixed(6)} · 均价 ${money(p.entry)}</p></div><div><b class="${p.unrealized>=0?'positive':'negative'}">${signed(p.unrealized)}</b><p>止损 ${money(p.stop)} · 价值 ${money(p.value)}</p></div></div>`).join(''):'<div class="empty"><strong>保持空仓，也是一种决策。</strong>等待符合策略与风控约束的信号</div>';
  $('latest-decision').innerHTML=preview(s.rounds[0]);
  $('trade-rows').innerHTML=s.trades.slice(0,20).map(t=>`<tr><td>${esc(stamp(t.time))}</td><td class="asset">${esc(t.symbol)}</td><td class="${t.side==='buy'?'positive':'negative'}">${t.side==='buy'?'↗ 买入':'↘ 卖出'}</td><td>${t.quantity.toFixed(6)}</td><td>${money(t.price)}</td><td>${money(t.fee)}</td><td class="${t.pnl===null?'muted':t.pnl>=0?'positive':'negative'}">${t.pnl===null?'—':signed(t.pnl)}</td><td>${esc(t.reason)}</td></tr>`).join('')||'<tr><td colspan="8" class="empty">尚无成交。推进模拟行情以观察策略执行。</td></tr>';
  // Preserve open snapshot details across polling updates.
  const openRounds=new Set([...document.querySelectorAll('#round-list details[open]')].map(el=>el.dataset.round));
  $('round-list').innerHTML=s.rounds.map(r=>`<article class="round"><div class="decision-meta"><span>ROUND #${r.id} · ${esc(stamp(r.time))} UTC</span><span class="${r.review.verdict==='approve'?'positive':'negative'}">${esc(r.review.verdict.toUpperCase())}</span></div><h3>${esc(r.proposal.regime)} · 风险倾向 ${pct(r.proposal.risk_scale)}</h3><p>${esc(r.proposal.thesis)}</p><p><b>Critic</b> / ${esc(r.review.reason)}</p><div class="round-outcomes">${r.outcomes.length?r.outcomes.map(o=>`${esc(o.symbol)} · ${o.status==='filled'?'成交':'拦截'} · ${esc(o.reason)}`).join('<br>'):r.review.verdict==='veto'?'提议被否决，本轮不执行订单。':'本轮无交易动作，保持现有状态。'}</div><details data-round="${r.id}" ${openRounds.has(String(r.id))?'open':''}><summary>查看输入快照与执行记录 · ${esc(r.provider)}</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details></article>`).join('')||'<div class="empty">尚无认知记录</div>';
  $('factor-rows').innerHTML=s.research.map(f=>`<tr><td>${esc(f.name)}<br><small class="muted">${esc(f.reason)}</small></td><td><span class="regime ${f.status==='Trial'?'':'range'}">${esc(f.status)}</span></td><td>${f.train.ic.toFixed(3)}</td><td class="${f.validation.ic>=0?'positive':'negative'}">${f.validation.ic.toFixed(3)}</td><td>${f.validation.rank_ic.toFixed(3)}</td><td>${f.validation.samples} / ${f.validation.trades} trades</td><td>${pct(f.validation.net_mean_return)}</td><td class="muted">未授权</td></tr>`).join('')||'<tr><td colspan="8" class="empty">点击「运行研究」评估第一组候选因子。</td></tr>';
  const details=[['交易环境','本地模拟 · 无交易所连接'],['行情来源','确定性合成 OHLCV'],['外部情报',h.news==='collector_connected'?'已连接，健康状况见情报中心':'未接入'],['认知引擎',s.provider],['模型费用',s.provider==='rules'?'0.00 USDC（未调用模型）':'未统计，查看模型提供商账单'],['模拟手续费',money(a.fees)+' USDC'],['市场快照年龄',h.snapshot_age===null?'等待新快照':h.snapshot_age.toFixed(1)+' 秒'+(h.snapshot_age>30?' · 已过期':'')],['风控巡检 / 模拟成交',h.risk_ticks+' / '+h.trade_count],['风险预算缩放',pct(h.risk_scale)],['自动运行频率','每 4 根 K 线认知 / 每 672 根研究'],['模拟时钟','每根 K 线 = 15 分钟']];
  $('system-details').innerHTML=details.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('');
  $('event-list').innerHTML=s.events.slice(0,40).map(e=>`<div class="event"><time>${esc(stamp(e.time))}</time><span>${esc(e.message)}</span></div>`).join('');
  $('last-update').textContent='最后同步 '+new Date().toLocaleTimeString('zh-CN');controls();
}
async function refresh(){
  try{const response=await fetch('/api/state');if(!response.ok)throw new Error('HTTP '+response.status);state=await response.json();render(state);$('connection-text').textContent='本地已连接';$('connection-dot').style.background='var(--green)';}
  catch(error){$('intel-decision-mode').textContent='暂时无法读取模拟账户状态。';$('connection-text').textContent='连接中断';$('connection-dot').style.background='var(--red)';$('error-banner').hidden=false;$('error-banner').textContent='无法获取最新状态，请检查本地服务。'+error.message;}
}
async function poll(){await refresh();setTimeout(poll,2500);}
controls();poll();
