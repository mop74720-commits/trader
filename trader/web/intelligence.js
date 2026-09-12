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
  let failedAppend = false;
  let searchTimer;
  let detailRequest = 0;
  let detailOrigin = null;
  const dateFormat = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
  const time = seconds => seconds == null ? '—' : dateFormat.format(new Date(seconds*1000));
  const day = seconds => time(seconds).slice(0,10);
  const tierName = {T1:'官方原文','T1.5':'官方频道',T2:'媒体报道',unrated:'来源待分级'};
  const reasonName = {asset_or_macro_match:'与你关注的资产或宏观政策相关',material_event_terms:'涉及政策、资金或市场运行的重要变化',first_party_source:'来自发布方的一手渠道',market_background:'补充市场背景'};
  const duration = seconds => seconds >= 86400 ? `${Math.round(seconds/86400)} 天` : seconds >= 3600 ? `${Math.round(seconds/3600)} 小时` : seconds < 60 ? '不到 1 分钟' : `${Math.round(seconds/60)} 分钟`;
  const health = {healthy:'正常',degraded:'部分来源异常',error:'读取失败',stale:'更新延迟',pending:'等待首次读取',disabled:'未启用'};
  const coverage = {latest_window:'公开内容的最近一段',top_volume_sample:'成交量较高的市场样本',recent_search_window:'X 的近期搜索结果',pagination_pending:'还有内容等待读取',configured_file:'指定的本地文件'};
  const sourceKind = {rss:'公开资讯源',telegram:'公开频道',polymarket:'预测市场',x:'X 搜索',jsonl:'本地文件'};
  const topic = {monetary_policy:'宏观政策',regulation:'监管',security:'安全事件',exchange:'交易所',derivatives:'衍生品',market:'市场'};
  const claimState = {reported:'报道称已发生',planned:'计划 / 预期',application:'申请 / 受理',uncertain:'传闻 / 不确定',denied:'否定 / 驳回',unknown:'进展待确认',market_quote:'预测合约'};
  const gapLabel = {publication_time_missing:'缺少发布时间',source_link_missing:'缺少原始链接',primary_evidence_unchecked:'还没有核对官方公告或最初报道',single_source_family:'现有报道可能来自同一出处，不能算多方确认',event_status_unknown:'仅凭标题还无法判断事情进展',conflicting_claims:'需核对冲突报道',orderbook_missing:'没有买卖盘数据，无法判断能否按这个价格成交',resolution_rules_unchecked:'尚未核对合约怎样判定结果',liquidity_missing:'缺少流动性数据'};
  const matchLabel = {holding:'与模拟持仓相关',watchlist:'与你关注的资产相关',macro:'宏观政策动态',general:'市场动态'};
  function qualityDetails(e) {
    const editorial=e.editorial || {};
    const dimensions=e.assessment?.dimensions || {};
    const gapItems=(e.evidence_gaps||[]).map(g=>`<li>${esc(gapLabel[g]||g)}</li>`).join('');
    const names={relevance:'关注相关',materiality:'事件影响线索',specificity:'信息具体程度',freshness:'时效',source_quality:'来源权重'};
    return `<details class="intel-quality" data-event="${esc(e.id)}"><summary>查看筛选依据与全部待核实项</summary>
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
    const primary=e.evidence[0];
    const related=(e.related_evidence || e.evidence).filter(p=>p.id!==primary.id);
    const reasons=(e.assessment?.reasons || []).map(r=>reasonName[r]).filter(Boolean);
    const unresolved=e.possible_conflict?'相关报道说法不一致，需对照原始发布。':(e.evidence_gaps||[]).slice(0,2).map(g=>gapLabel[g]||g).join('；') || '尚未独立核实。';
    const status=claimState[e.claim?.status] || '进展待确认';
    return `<article class="intel-event" id="event-${esc(e.id)}"><div class="intel-event-head"><time title="${time(at)} 北京时间">${time(at).slice(11)} <small>${quote?'读取':e.published_at==null?'收录':'发布'}</small></time><span class="intel-source-name">${esc(primary.source)}</span><span class="intel-tier">${esc(quote?'预测市场报价':tierName[e.source_tier]||tierName.unrated)}</span>${!quote?`<span class="intel-score ${e.editorial?.selected?'selected':''}">${e.editorial?.selected?'规则精选':'相关报道'}</span>`:''}</div>
      <h3>${safeLink(primary.url)?`<a href="${safeLink(primary.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a>`:esc(e.title)}</h3>
      ${!quote && e.summary.trim()!==e.title.trim()?`<p class="intel-excerpt"><span class="intel-text-label">原文摘录</span>${esc(e.summary)}</p>`:''}
      <dl class="intel-story-facts">
        <div><dt>关联资产</dt><dd>${e.assets.length?e.assets.map(a=>`<button class="intel-asset" data-intel-asset="${esc(a)}" aria-label="搜索 ${esc(a)} 相关信息">${esc(a)}</button>`).join(''):'未识别到具体资产'}<span class="intel-context">${esc(topic[e.category]||'市场')} · ${esc(matchLabel[e.context_match]||'市场动态')}</span></dd></div>
        <div><dt>${quote?'报价含义':'报道进展'}</dt><dd>${quote?'市场参与者的预期，不代表事件已发生。':`${esc(status)}<span class="intel-context">根据标题识别，尚未独立核实</span>`}</dd></div>
        <div><dt>市场反应</dt><dd class="intel-unavailable">暂无真实行情对照，暂不判断是否已反映在价格中。</dd></div>
        <div><dt>待核实</dt><dd class="${e.possible_conflict?'intel-conflict':'intel-caution'}">${esc(unresolved)}</dd></div>
      </dl>
      ${quote?`<div class="intel-quotes">${(e.metrics.outcomes||[]).map(q=>`${esc(q.outcome)} ${(q.price*100).toFixed(1)}%`).join(' / ') || '暂时没有报价'}<br>流动性 ${e.metrics.liquidity==null?'未知':money(e.metrics.liquidity)} · 24 小时成交量 ${e.metrics.volume24hr==null?'未知':money(e.metrics.volume24hr)}</div><p class="intel-small-note">显示价不保证可成交；需查看盘口及合约结算规则。</p>`:`<p class="intel-recommendation"><span>为何展示</span>${esc(reasons.join('；')||'补充市场背景')}。</p>`}
      <div class="intel-story-footer">${safeLink(primary.url)?`<a class="intel-inline-link" href="${safeLink(primary.url)}" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a>`:''}<button class="text-button" data-evidence="${esc(primary.id)}">查看来源记录</button>${related.length?`<details class="intel-related" data-event="related-${esc(e.id)}"><summary>另有 ${related.length} 条相关记录</summary>${related.map(p=>`<div class="intel-related-row"><p>${esc(p.title||p.quote)}</p><small>${time(p.published_at??p.observed_at)} · ${esc(tierName[p.tier]||tierName.unrated)}</small>${citation(p)}</div>`).join('')}</details>`:'<span>目前仅收录这一条来源记录</span>'}</div>
      ${qualityDetails(e)}</article>`;
  }
  async function loadFeed(append=false) {
    const request=++feedRequest;
    const requestedReplay=Boolean(replay);
    feedLoading=true;
    $('intel-view-status').textContent=append?'正在加载更多…':'正在筛选信息…';
    $('intel-load-more').disabled=true;
    $('intel-refresh').disabled=true;
    $('intel-feed-retry').disabled=true;
    $('intel-events').setAttribute('aria-busy','true');
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
      const previous=feedData;
      feedData=result;
      try {renderDigest();} catch(error) {feedData=previous;throw error;}
      $('intel-feed-problem').hidden=true;
    } catch(error) {
      if(request===feedRequest) {
        failedAppend=append;
        $('intel-feed-problem').hidden=false;
        $('intel-feed-problem-text').textContent=(error.name==='AbortError'?'读取列表超时。':'这次未能读取列表。')+(feedData?'下方保留上次成功读取的内容，本次筛选或更新尚未应用。':'请重试；若仍失败，请检查本地服务。');
        $('intel-view-status').textContent='更新未完成。';
        if(!feedData) {
          $('intel-brief-title').textContent='暂时无法读取简报';
          $('intel-brief-scope').textContent='尚未取得统计结果，请重试列表。';
          $('intel-highlights').innerHTML='<li class="muted">列表恢复后显示速读内容。</li>';
        }
      }
    } finally {if(request===feedRequest){feedLoading=false;$('intel-load-more').disabled=false;$('intel-refresh').disabled=false;$('intel-feed-retry').disabled=false;$('intel-events').setAttribute('aria-busy','false');}}
  }
  const safeLink = url => /^https?:\/\//i.test(url) ? esc(url) : '';
  async function get(path) {
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),15000);
    try {
      const response=await fetch(path,{signal:controller.signal});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {clearTimeout(timeout);}
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
    const sourceName=current?.status.sources.find(p=>p.id===digest.feed.source_id)?.name || digest.feed.source_id;
    const range=digest.feed.window==='24h'?'过去 24 小时':'过去 7 天';
    const scope=[range,displayedCategory?topic[displayedCategory]:'全部类别',sourceName||'全部来源',digest.feed.query.trim()?`搜索「${digest.feed.query}」`:''].filter(Boolean).join(' · ');
    $('intel-quality-summary').textContent=focus.length?`${historical?'本次历史查询':'当前账户'}的关注范围：${focus.join('、')}。`:(historical?'历史查询未指定资产，按通用市场视角整理。':'当前未指定关注资产，按通用市场视角整理。');
    $('intel-focus-assets').innerHTML=focus.map(a=>`<button class="intel-asset" data-intel-asset="${esc(a)}">${esc(a)}</button>`).join('');
    $('intel-digest-time').textContent=`列表截至 ${time(digest.as_of)}`;
    $('intel-feed-title').textContent={selected:'精选报道',timeline:'全部相关报道',quotes:'预测市场报价'}[displayedMode];
    const selectedCount=digest.feed.counts.selected;
    $('intel-brief-title').textContent=selectedCount?`当前范围内，${selectedCount} 条报道入选`:'当前范围暂无入选报道';
    $('intel-brief-scope').textContent=`${historical?'历史查询 · ':''}截至 ${time(digest.as_of)} · ${scope}。`;
    $('intel-brief-selected').textContent=selectedCount;
    $('intel-brief-total').textContent=digest.feed.counts.timeline;
    $('intel-view-status').textContent=`已加载 ${events.length} / ${digest.feed.matched_total} 条 · ${scope}`;
    $('intel-view-description').textContent={selected:'依据相关性、时效和来源等规则筛选；入选不代表已经证实。',timeline:'当前来源中通过相关性与有效期检查的报道，包含未入选内容。',quotes:'预测合约报价单独展示，不是新闻事实，也不代表客观发生概率。'}[displayedMode];
    $('intel-history-banner').hidden=!historical;
    $('intel-history-banner').textContent=`正在查看 ${time(digest.as_of)} 前已采集的信息。使用当前筛选规则；右侧运行状态为当前状态。`;
    $('intel-live').hidden=!historical;
    $('intel-refresh').textContent=historical?'重载历史列表 ↻':'刷新列表 ↻';
    $('intel-load-more').hidden=digest.feed.next_offset==null;
    $('intel-read-first-title').textContent=displayedMode==='quotes'?'最近更新的报价':'先读这几条';
    $('intel-read-first-note').textContent=`从当前${displayedMode==='selected'?'精选报道':displayedMode==='timeline'?'全部报道':'报价'}中按时间取前 3 条，点击跳到详情。`;
    $('intel-highlights').innerHTML=events.slice(0,3).map((e,i)=>`<li><span>0${i+1}</span><button data-scroll-event="${esc(e.id)}">${esc(e.title)}</button><small>${esc(e.assets.join(' / ')||'市场动态')}</small></li>`).join('') || '<li class="muted">此范围暂无可读内容。可扩大时间范围或清除筛选。</li>';
    ['selected','timeline','quotes'].forEach(k=>{$('intel-count-'+k).textContent=digest.feed.counts[k];});
    document.querySelectorAll('[data-intel-mode]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.intelMode===displayedMode)));
    document.querySelectorAll('[data-intel-category]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.intelCategory===displayedCategory)));
    const f=digest.funnel;
    $('intel-funnel').innerHTML=[['收到的条目',f.observed_items],['过滤后保留',f.eligible_items],['合并后条目',f.clustered_events],['其中精选报道',f.selected_reports]].map(([label,count])=>`<li><span>${label}</span><strong>${count}</strong></li>`).join('')+`<li class="intel-funnel-note">合并了 ${f.merged_reports} 条重复记录 · ${f.market_quotes} 个预测报价单独展示</li>`;
    $('intel-policy-id').textContent='筛选版本 '+digest.curation_policy.version+' · '+digest.curation_policy.id;
    const opened=new Set([...document.querySelectorAll('#intel-events details[open]')].map(el=>el.dataset.event));
    const active=document.activeElement;
    const focusedEvent=active?.matches('#intel-events summary')?active.closest('details').dataset.event:null;
    const focusedEvidence=active?.dataset.evidence;
    const groups=new Map();
    events.forEach(e=>{const key=day(e.kind==='prediction_market'?e.last_observed_at:e.timeline_at);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e);});
    let html=[...groups].map(([date,rows])=>`<div class="intel-day"><strong>${date}</strong><span>${rows.length} 条 · 北京时间</span></div>${rows.map(renderEvent).join('')}`).join('');
    if(!html) html=`<div class="empty"><strong>${filtered?'没有找到匹配的信息':displayedMode==='selected'?'这个时间范围暂无入选报道':'这个时间范围暂无可显示的信息'}</strong><p>${displayedMode==='selected'?'可以切换到全部报道，或将时间范围扩大到过去 7 天。':'试试扩大时间范围，或调整类别与来源。'}</p>${displayedMode==='selected'?'<button data-intel-mode="timeline">查看全部报道</button>':''}${filtered?'<button id="intel-reset-filters">清除筛选</button>':''}</div>`;
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
    const enabled=s.sources.filter(p=>p.enabled);
    const healthy=enabled.filter(p=>p.health==='healthy').length;
    const attempts=enabled.map(p=>p.last_success).filter(Number.isFinite);
    $('intel-health').textContent=s.collecting?'正在检查外部来源':health[s.health]||s.health;
    $('intel-source-count').textContent=`${enabled.length} 个已启用来源 · ${healthy} 个最近读取正常`;
    $('intel-source-freshness').textContent=attempts.length?`最近一次来源读取成功：${time(Math.max(...attempts))}。其余来源状态见下方目录。`:'尚无成功读取记录，可展开来源目录查看原因。';
    $('intel-tier-sources').innerHTML=['T1','T1.5','T2','unrated'].map(t=>{
      const sources=s.sources.filter(p=>p.enabled && p.tier===t);
      return sources.length?`<div class="intel-tier-group"><div><b>${esc(tierName[t])}</b><p>${sources.map(p=>esc(p.name.split(' · ')[0])).join('、')}</p></div></div>`:'';
    }).join('');
    $('intel-collect').textContent=s.collecting?'正在检查来源…':'检查信源';
    $('intel-collect').disabled=s.collecting||pending;
    const selection=$('intel-source-filter').value;
    $('intel-source-filter').innerHTML='<option value="">全部来源</option>'+s.sources.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    $('intel-source-filter').value=selection;
    $('intel-sources').innerHTML=s.sources.map(p=>`<tr><td>${esc(p.name)}<br><small class="muted">${esc(tierName[p.tier]||tierName.unrated)} · ${esc(sourceKind[p.kind]||p.kind)}<br>${esc(p.editorial_note||'尚未填写采用理由')}</small></td><td class="${p.health==='healthy'?'positive':p.health==='error'?'negative':'muted'}">${esc(health[p.health]||p.health)}${sourceIssue(p)}</td><td>${time(p.last_success)}</td><td>${p.fetched_items??'—'} / ${p.new_versions??'—'}</td><td>${duration(p.interval_seconds)} / ${duration(p.ttl_seconds)}</td><td>${esc(coverage[p.coverage]||'尚未读取')}<br><small class="muted">下次 ${time(p.next_poll)}</small></td></tr>`).join('');
    $('intel-evidence').innerHTML=current.recent.map(p=>`<tr><td class="intel-evidence-title">${esc(p.title)}</td><td>${esc(p.source_name)}</td><td class="${p.quarantined?'negative':'muted'}">${p.quarantined?'暂不采用':!p.relevant?'暂不相关':'已保存'}${p.quarantined?'<br><small>含指令样式文本或异常发布时间</small>':''}</td><td>第 ${p.revision} 版</td><td>${time(p.observed_at)}</td><td><button class="text-button" data-evidence="${esc(p.id)}">查看 ↗</button></td></tr>`).join('') || '<tr><td colspan="6" class="empty">还没有读取记录</td></tr>';
    $('intel-notifications').innerHTML=current.notifications.map(n=>`<div class="event"><time>${time(n.observed_at)}</time><span>${n.reason==='quote_price_change'?'报价累计变化 '+(n.max_price_change*100).toFixed(1)+' 个百分点':n.kind==='revision'?'内容有更新':'发现新信息'} · ${esc(n.title)}</span></div>`).join('') || '<div class="empty">暂时没有提醒</div>';
  }
  async function refreshIntel() {
    try {
      current=await get('/api/intelligence');
      const unavailable=current.status.sources.filter(p=>p.enabled && p.health!=='healthy').length;
      $('intel-error').hidden=!unavailable && !current.status.last_error;
      $('intel-error').textContent=unavailable?`当前有 ${unavailable} 个来源尚未就绪、读取异常或延迟，最新信息可能不完整。可展开下方来源目录查看原因。`:'来源检查暂时遇到问题，系统会重试。已有列表仍可阅读。';
      render();
    } catch(error) {
      $('intel-health').textContent='来源状态连接中断';
      $('intel-error').hidden=false;
      $('intel-error').textContent=current?'暂时无法读取来源状态，下方保留上次记录。系统会自动重试连接。':'暂时无法读取来源状态。可重试列表，或检查本地服务是否启用了信息采集。';
    }
  }
  $('intel-refresh').addEventListener('click',()=>loadFeed());
  $('intel-feed-retry').addEventListener('click',()=>loadFeed(failedAppend));
  $('intel-source-filter').addEventListener('change',()=>loadFeed());
  $('intel-window').addEventListener('change',()=>loadFeed());
  $('intel-load-more').addEventListener('click',()=>loadFeed(true));
  $('intel-search').maxLength=200;
  $('intel-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadFeed(),250);});
  $('intel-collect').addEventListener('click',async()=>{
    pending=true;$('intel-collect').disabled=true;
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),15000);
    try {
      const r=await fetch('/api/intelligence/collect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:controller.signal});
      if(!r.ok)throw new Error((await r.json()).error);
      toast('已请求检查来源。完成后点击刷新列表查看结果；未到读取时间的来源会继续等待。');
      await refreshIntel();
    } catch(error) {toast('未能请求检查来源，请稍后重试。已有列表仍可阅读。');} finally {clearTimeout(timer);pending=false;$('intel-collect').disabled=Boolean(current?.status.collecting);}
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
    const jump=event.target.closest('[data-scroll-event]');
    if(jump) {
      const target=$('event-'+jump.dataset.scrollEvent);
      if(target){target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:'start'});}
      return;
    }
    const asset=event.target.closest('[data-intel-asset]');
    if(asset){feedMode='timeline';$('intel-search').value=asset.dataset.intelAsset;await loadFeed();$('intel-search').focus({preventScroll:true});return;}

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
  loadFeed();
  pollIntel();
})();
