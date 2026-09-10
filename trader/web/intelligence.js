'use strict';
(() => {
  let current = null;
  let replay = null;
  let pending = false;
  let feedData = null;
  let feedMode = 'selected';
  let feedCategory = '';
  let feedRequest = 0;
  let feedLoading = false;
  let searchTimer;
  let detailRequest = 0;
  let detailOrigin = null;
  const dateFormat = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
  const time = seconds => seconds == null ? '—' : dateFormat.format(new Date(seconds*1000));
  const day = seconds => time(seconds).slice(0,10);
  const tierName = {T1:'官网 / 一手发布','T1.5':'官方社交频道',T2:'媒体 / 其他来源',unrated:'未分级'};
  const reasonName = {asset_or_macro_match:'与你关注的资产或宏观政策相关',material_event_terms:'涉及政策、资金或市场运行的重要变化',first_party_source:'来自发布方的一手渠道',market_background:'补充市场背景'};
  const duration = seconds => seconds >= 86400 ? `${Math.round(seconds/86400)} 天` : seconds >= 3600 ? `${Math.round(seconds/3600)} 小时` : seconds < 60 ? '不到 1 分钟' : `${Math.round(seconds/60)} 分钟`;
  const health = {healthy:'正常',degraded:'部分来源异常',error:'读取失败',stale:'更新延迟',pending:'等待首次读取',disabled:'未启用'};
  const coverage = {latest_window:'公开内容的最近一段',top_volume_sample:'成交量较高的市场样本',recent_search_window:'X 的近期搜索结果',pagination_pending:'还有内容等待读取',configured_file:'指定的本地文件'};
  const sourceKind = {rss:'公开资讯源',telegram:'公开频道',polymarket:'预测市场',x:'X 搜索',jsonl:'本地文件'};
  const topic = {monetary_policy:'宏观政策',regulation:'监管',security:'安全事件',exchange:'交易所',derivatives:'衍生品',market:'市场'};
  const claimState = {reported:'报道称已发生',planned:'计划 / 预期',application:'申请 / 受理',uncertain:'传闻 / 不确定',denied:'否定 / 驳回',unknown:'进展待确认',market_quote:'预测合约'};
  const gapLabel = {publication_time_missing:'缺少发布时间',source_link_missing:'缺少原始链接',primary_evidence_unchecked:'还没有核对官方公告或最初报道',single_source_family:'现有报道可能来自同一出处，不能算多方确认',event_status_unknown:'仅凭标题还无法判断事情进展',conflicting_claims:'需核对冲突报道',orderbook_missing:'没有买卖盘数据，无法判断能否按这个价格成交',resolution_rules_unchecked:'尚未核对合约怎样判定结果',liquidity_missing:'缺少流动性数据'};
  const matchLabel = {holding:'与你的持仓相关',watchlist:'与你关注的资产相关',macro:'宏观政策动态',general:'市场动态'};
  function qualityDetails(e) {
    const editorial=e.editorial || {};
    const dimensions=e.assessment?.dimensions || {};
    const gapItems=(e.evidence_gaps||[]).map(g=>`<li>${esc(gapLabel[g]||g)}</li>`).join('');
    const names={relevance:'关注相关',materiality:'事件影响线索',specificity:'信息具体程度',freshness:'时效',source_quality:'来源权重'};
    return `<details class="intel-quality" data-event="${esc(e.id)}"><summary>筛选依据与待核实事项</summary>
      <div class="intel-dimension-scores">${Object.entries(dimensions).map(([k,v])=>`<span>${names[k]||esc(k)} <b>${v}</b></span>`).join('')}</div>
      <p>规则评分 ${editorial.score??'—'}，当前类别门槛 ${editorial.threshold??'—'}。${editorial.reason==='market_quote'?'市场报价不参加新闻精选。':editorial.selected?'达到精选门槛。':'未达到精选门槛，仍保留在全部动态中。'}</p>
      <ul>${gapItems}</ul><p>标题进展由规则推测。相关记录 ${e.evidence_count} 条，自动去重后估计 ${e.independent_reports} 组来源，不能据此证明互相独立。</p>
      <p class="muted">评分用于筛选，不是可信度或买卖建议。</p></details>`;
  }
  function sourceError(code) {
    if (/429|rate_limit/.test(code)) return '来源限制了读取频率，将稍后重试';
    if (/401|403|credential|token|x_api_not_enabled/.test(code)) return '暂时无法访问，请检查来源设置';
    if (/Timeout|timeout/.test(code)) return '来源响应较慢，将自动重试';
    return '这次未能读取，已保留上次内容并安排重试';
  }
  function sourceIssue(p) {
    return p.error?`<p class="intel-source-error">${sourceError(p.error)}</p><details><summary>错误详情</summary><code>${esc(p.error)}</code></details>`:'';
  }
  function citation(p) {
    return `<div class="intel-citation">${safeLink(p.url)?`<a href="${safeLink(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.source)} ↗</a>`:esc(p.source)}<button data-evidence="${esc(p.id)}" aria-label="查看${esc(p.source)}的来源记录">查看记录</button></div>`;
  }
  function renderEvent(e) {
    const quote=e.kind==='prediction_market';
    const at=quote?e.last_observed_at:e.timeline_at;
    const state=claimState[e.claim?.status];
    const primary=e.evidence[0];
    const related=(e.related_evidence || e.evidence).filter(p=>p.id!==primary.id);
    const reasons=(e.assessment?.reasons || []).map(r=>reasonName[r]).filter(Boolean);
    return `<article class="intel-event" id="event-${esc(e.id)}"><div class="intel-event-head"><time title="${time(at)} 北京时间">${time(at).slice(11)} <small>${quote?'读取':e.published_at==null?'收录':'发布'}</small></time><span class="intel-source-name">${esc(primary.source)}</span><span class="intel-tier">${esc(quote?'报价':e.source_tier==='unrated'?'未分级':e.source_tier)}</span>${!quote?`<span class="intel-score ${e.editorial?.selected?'selected':''}" title="规则评分，不是事实正确率">${e.editorial?.selected?'精选':'评分'} ${Math.round(e.editorial?.score||0)}</span>`:''}</div>
      <h3>${safeLink(primary.url)?`<a href="${safeLink(primary.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a>`:esc(e.title)}</h3>
      <div class="intel-tags">${e.assets.map(a=>`<span>${esc(a)}</span>`).join('')}<span>${esc(topic[e.category]||'市场')}</span>${!quote && state && e.claim?.status!=='unknown'?`<span>${esc(state)}</span>`:''}${e.possible_conflict?'<span class="conflict">报道说法不一致</span>':''}</div>
      ${!quote && e.summary.trim()!==e.title.trim()?`<p class="intel-excerpt">${esc(e.summary)}</p>`:''}
      ${quote?`<div class="intel-quotes">${(e.metrics.outcomes||[]).map(q=>`${esc(q.outcome)} ${(q.price*100).toFixed(1)}%`).join(' / ') || '暂时没有报价'}<br>流动性 ${e.metrics.liquidity==null?'未知':money(e.metrics.liquidity)} · 24 小时成交量 ${e.metrics.volume24hr==null?'未知':money(e.metrics.volume24hr)}</div><p class="intel-small-note">报价不表示事件已经发生，也不保证能按此价格成交。</p>`:`<p class="intel-recommendation"><span>${e.editorial?.selected?'入选理由':'相关线索'}</span>${esc(reasons.join('；')||'市场背景信息')}。</p>`}
      <div class="intel-story-footer"><button class="text-button" data-evidence="${esc(primary.id)}">原文与记录 ↗</button>${related.length?`<details class="intel-related" data-event="related-${esc(e.id)}"><summary>另有 ${related.length} 条相关报道</summary>${related.map(p=>`<div class="intel-related-row"><p>${esc(p.title||p.quote)}</p><small>${time(p.published_at??p.observed_at)} · ${esc(p.tier||'unrated')}</small>${citation(p)}</div>`).join('')}</details>`:'<span>暂只有这一条报道</span>'}</div>
      ${qualityDetails(e)}</article>`;
  }
  async function loadFeed(append=false) {
    const request=++feedRequest;
    const requestedReplay=Boolean(replay);
    feedLoading=true;
    $('intel-view-status').textContent=append?'正在加载更多…':'正在筛选信息…';
    $('intel-load-more').disabled=true;
    const params=new URLSearchParams({mode:feedMode,category:feedCategory,source:$('intel-source-filter').value,q:$('intel-search').value,window:$('intel-window').value,limit:'30'});
    if(append && feedData) {
      params.set('offset',feedData.feed.next_offset);
      params.set('as_of',new Date(feedData.as_of*1000).toISOString());
      params.set('assets',feedData.context.watchlist.join(',') || ',');
      params.set('holdings',feedData.context.holdings.join(',') || ',');
    } else if(replay) params.set('as_of',replay);
    try {
      const result=await get('/api/intelligence/feed?'+params);
      if(request!==feedRequest)return;
      if(append) result.events=[...feedData.events,...result.events];
      result.view_replay=requestedReplay;
      feedData=result;
      renderDigest();
    } catch(error) {
      if(request===feedRequest) $('intel-view-status').textContent='暂时无法更新此列表，请稍后点击检查更新。';
    } finally {if(request===feedRequest){feedLoading=false;$('intel-load-more').disabled=false;}}
  }
  const safeLink = url => /^https?:\/\//i.test(url) ? esc(url) : '';
  async function get(path) {
    const response = await fetch(path);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    return result;
  }
  function renderDigest() {
    if(!feedData)return;
    const digest=feedData;
    const events=digest.events;
    const displayedMode=digest.feed.mode;
    const displayedCategory=digest.feed.category;
    const historical=digest.view_replay;
    const filtered=Boolean(displayedCategory || digest.feed.source_id || digest.feed.query.trim());
    const focus=[...new Set([...(digest.context?.holdings||[]),...(digest.context?.watchlist||[])])];
    $('intel-quality-summary').textContent=focus.length?`围绕 ${focus.join('、')}，优先保留与当前关注范围相关的信息。`:'按通用市场视角整理当时的信息。';
    $('intel-digest-time').textContent=`${time(digest.as_of)} 北京时间`;
    $('intel-feed-title').textContent={selected:'重要信息',timeline:'全部信息',quotes:'市场预期'}[displayedMode];
    const selectedCount=digest.feed.counts.selected;
    $('intel-brief-title').textContent=selectedCount?`发现 ${selectedCount} 条重要信息`:'暂时没有重要信息';
    $('intel-view-status').textContent=`${historical?'历史快照 · ':''}当前显示 ${events.length} 条，共匹配 ${digest.feed.matched_total} 条 · ${displayedMode==='selected'?'系统判断为重要的信息':displayedMode==='timeline'?'相关信息，包含待进一步确认的内容':'市场参与者的预期报价'}${events.length>30?' · 加载更多时固定查询时间，点击检查更新返回最新快照':''}`;
    $('intel-live').hidden=!historical;
    $('intel-load-more').hidden=digest.feed.next_offset==null;
    ['selected','timeline','quotes'].forEach(k=>{$('intel-count-'+k).textContent=digest.feed.counts[k];});
    document.querySelectorAll('[data-intel-mode]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.intelMode===displayedMode)));
    document.querySelectorAll('[data-intel-category]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.intelCategory===displayedCategory)));
    const f=digest.funnel;
    $('intel-funnel').innerHTML=[['读取条目',f.observed_items],['通过预筛',f.eligible_items],['合并后事件',f.clustered_events],['新闻精选',f.selected_reports]].map(([label,count],n)=>`<li><span><small>0${n+1}</small>${label}</span><strong>${count}</strong></li>`).join('')+`<li class="intel-funnel-note">${f.merged_reports} 条重复报道已合并 · ${f.market_quotes} 个市场报价单独展示</li>`;
    $('intel-policy-id').textContent='筛选版本 '+digest.curation_policy.version+' · '+digest.curation_policy.id;
    const opened=new Set([...document.querySelectorAll('#intel-events details[open]')].map(el=>el.dataset.event));
    const active=document.activeElement;
    const focusedEvent=active?.matches('#intel-events summary')?active.closest('details').dataset.event:null;
    const focusedEvidence=active?.dataset.evidence;
    const groups=new Map();
    events.forEach(e=>{const key=day(e.kind==='prediction_market'?e.last_observed_at:e.timeline_at);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e);});
    let html=[...groups].map(([date,rows])=>`<div class="intel-day"><strong>${date}</strong><span>${rows.length} 条 · 北京时间</span></div>${rows.map(renderEvent).join('')}`).join('');
    if(!html) html=`<div class="empty"><strong>${filtered?'没有找到匹配的信息':displayedMode==='selected'?'这个时间范围暂无入选报道':'这个时间范围暂无可显示的信息'}</strong><p>${displayedMode==='selected'?'可以切换到全部动态，查看相关但未达到精选门槛的报道。':'试试扩大时间范围，或调整类别与来源。'}</p>${displayedMode==='selected'?'<button data-intel-mode="timeline">查看全部动态</button>':''}${filtered?'<button id="intel-reset-filters">清除筛选</button>':''}</div>`;
    if($('intel-events').dataset.rendered!==html) {
      $('intel-events').innerHTML=html;
      $('intel-events').dataset.rendered=html;
      document.querySelectorAll('#intel-events details').forEach(el=>{
        el.open=opened.has(el.dataset.event);
        if(el.dataset.event===focusedEvent)el.querySelector('summary').focus({preventScroll:true});
      });
      if(focusedEvidence)[...document.querySelectorAll('#intel-events [data-evidence]')].find(el=>el.dataset.evidence===focusedEvidence)?.focus({preventScroll:true});
    }
  }

  function render() {
    const s=current.status;
    $('intel-health').textContent=health[s.health]||s.health;
    $('intel-source-count').textContent=`正在关注 ${s.sources.filter(s=>s.enabled).length} 个来源`;
    $('intel-tier-sources').innerHTML=['T1','T1.5','T2','unrated'].map(t=>{
      const sources=s.sources.filter(p=>p.enabled && p.tier===t);
      return sources.length?`<div class="intel-tier-group"><span>${esc(t==='unrated'?'报价 / 未分级':t)}</span><div><b>${esc(tierName[t])}</b><p>${sources.map(p=>esc(p.name.split(' · ')[0])).join('、')}</p></div></div>`:'';
    }).join('');
    $('intel-collect').textContent=s.collecting?'正在读取…':'检查更新 ↻';
    $('intel-collect').disabled=s.collecting||pending;
    const selection=$('intel-source-filter').value;
    $('intel-source-filter').innerHTML='<option value="">全部来源</option>'+s.sources.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    $('intel-source-filter').value=selection;
    $('intel-sources').innerHTML=s.sources.map(p=>`<tr><td>${esc(p.name)}<br><small class="muted">${esc(p.tier||'未分级')} · ${esc(sourceKind[p.kind]||p.kind)}<br>${esc(p.editorial_note||'尚未填写采用理由')}</small></td><td class="${p.health==='healthy'?'positive':p.health==='error'?'negative':'muted'}">${esc(health[p.health]||p.health)}${sourceIssue(p)}</td><td>${time(p.last_success)}</td><td>${p.fetched_items??'—'} / ${p.new_versions??'—'}</td><td>${duration(p.interval_seconds)} / ${duration(p.ttl_seconds)}</td><td>${esc(coverage[p.coverage]||'尚未读取')}<br><small class="muted">下次 ${time(p.next_poll)}</small></td></tr>`).join('');
    $('intel-evidence').innerHTML=current.recent.map(p=>`<tr><td class="intel-evidence-title">${esc(p.title)}</td><td>${esc(p.source_name)}</td><td class="${p.quarantined?'negative':'muted'}">${p.quarantined?'暂不采用':!p.relevant?'暂不相关':'已保存'}${p.quarantined?'<br><small>含指令样式文本或异常发布时间</small>':''}</td><td>第 ${p.revision} 版</td><td>${time(p.observed_at)}</td><td><button class="text-button" data-evidence="${esc(p.id)}">查看 ↗</button></td></tr>`).join('') || '<tr><td colspan="6" class="empty">还没有读取记录</td></tr>';
    $('intel-notifications').innerHTML=current.notifications.map(n=>`<div class="event"><time>${time(n.observed_at)}</time><span>${n.reason==='quote_price_change'?'报价累计变化 '+(n.max_price_change*100).toFixed(1)+' 个百分点':n.kind==='revision'?'内容有更新':'发现新信息'} · ${esc(n.title)}</span></div>`).join('') || '<div class="empty">暂时没有提醒</div>';
    renderDigest();
  }
  async function refreshIntel(updateFeed=true) {
    try {
      current=await get('/api/intelligence');
      $('intel-error').hidden=!current.status.last_error;
      $('intel-error').textContent=current.status.last_error ? '自动更新暂时遇到问题，系统会重试。下方保留最近一次读取到的信息。' : '';
      render();
      if(updateFeed && !feedLoading && (!feedData || (!replay && feedData.events.length<=30))) await loadFeed();
    } catch(error) {
      $('intel-error').hidden=false;
      $('intel-error').textContent=current?'暂时无法获取更新，以下是上次读取的内容。系统会自动重试。':'暂时无法连接信息服务，系统会自动重试。请确认本地服务正在运行。';
    }
  }
  $('intel-source-filter').addEventListener('change',()=>loadFeed());
  $('intel-window').addEventListener('change',()=>loadFeed());
  $('intel-load-more').addEventListener('click',()=>loadFeed(true));
  $('intel-search').maxLength=200;
  $('intel-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadFeed(),250);});
  $('intel-collect').addEventListener('click',async()=>{
    pending=true;$('intel-collect').disabled=true;
    try {
      const r=await fetch('/api/intelligence/collect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      if(!r.ok)throw new Error((await r.json()).error);
      toast('已检查更新。各来源按自己的时间表读取，新内容会自动显示。');
      await refreshIntel(false);
      await loadFeed();
    } catch(error) {toast('未能检查更新，请稍后再试。');} finally {pending=false;$('intel-collect').disabled=Boolean(current?.status.collecting);}
  });
  $('intel-replay').addEventListener('click',async()=>{
    const value=$('intel-asof').value;
    if(!value || !Number.isFinite(new Date(value).getTime())) {
      toast('请先选择要查看的日期和时间。');
      $('intel-asof').focus();
      return;
    }
    replay=new Date(value).toISOString();
    $('intel-replay').disabled=true;
    try {await loadFeed();} finally {$('intel-replay').disabled=false;}
  });
  $('intel-live').addEventListener('click',()=>{replay=null;$('intel-asof').value='';loadFeed();$('intel-search').focus();});
  $('intel-detail-close').addEventListener('click',()=>{
    detailRequest++;
    $('intel-detail').hidden=true;
    const button=[...document.querySelectorAll('[data-evidence]')].find(el=>el.dataset.evidence===detailOrigin);
    if(button)button.focus();else $('intel-search').focus();
  });
  $('intelligence').addEventListener('click',async event=>{
    const modeButton=event.target.closest('[data-intel-mode]');
    if(modeButton){feedMode=modeButton.dataset.intelMode;loadFeed();return;}
    const categoryButton=event.target.closest('[data-intel-category]');
    if(categoryButton){feedCategory=categoryButton.dataset.intelCategory;loadFeed();return;}
    if(event.target.closest('#intel-reset-filters')) {
      feedCategory='';$('intel-source-filter').value='';$('intel-search').value='';loadFeed();$('intel-search').focus();return;
    }
    const button=event.target.closest('[data-evidence]');
    if(!button)return;
    const request=++detailRequest;
    try {
      const proof=await get('/api/intelligence/evidence/'+encodeURIComponent(button.dataset.evidence));
      if(request!==detailRequest)return;
      detailOrigin=button.dataset.evidence;
      $('intel-detail-content').innerHTML=`<h3>${esc(proof.title)}</h3><dl><div><dt>来源</dt><dd>${esc(proof.source_name)}</dd></div><div><dt>来源发布时间 · 北京时间</dt><dd>${proof.published_at==null?'来源未提供':time(proof.published_at)}</dd></div><div><dt>首次读到此版本 · 北京时间</dt><dd>${time(proof.observed_at)}</dd></div><div><dt>保存版本</dt><dd>第 ${proof.revision} 版</dd></div></dl><p>${esc(proof.text)}</p>${safeLink(proof.url)?`<a class="intel-original" href="${safeLink(proof.url)}" target="_blank" rel="noopener noreferrer">到来源网站查看原文 ↗</a>`:'<p class="muted">这条记录没有提供原始链接。</p>'}`;
      $('intel-detail-json').textContent=JSON.stringify(proof,null,2);
      $('intel-detail').querySelector('details').open=false;
      $('intel-detail').hidden=false;
      $('intel-detail-title').focus({preventScroll:true});
      $('intel-detail').scrollIntoView({behavior:'smooth',block:'start'});
    } catch(error){toast('暂时无法打开这条记录，请稍后再试。');}
  });
  async function pollIntel(){await refreshIntel();setTimeout(pollIntel,10000);}
  pollIntel();
})();
