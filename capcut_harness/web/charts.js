// tasteskill / charts.js — small, dependency-free charts for app screens, drawn in SVG from your data.
// They follow references/app-screens.md: one question per chart, one series that matters, 3–5 quiet
// horizontal gridlines, round ticks that top out above the largest value, 2px straight lines with no
// markers, square bars, no gradients, a bare tooltip, tabular figures. Colours come from CSS variables:
//   --chart-1 … --chart-4 (series), --chart-muted (other series), --chart-mark (a marked period; ink by default),
//   --chart-span (the opacity of a shaded span: about .06 on light, .12 on dark), --chart-track (a time strip's track),
//   --grid, --axis-ink, --ink, --surface, --raised, --rule, --negative
// Usage (after this file loads):
//   Charts.line(el, { labels: ['1 Oct', …], series: [{ name: 'Requests', values: [...] }], format: Charts.fmt.compact })
//   Charts.bars(el, { labels, values, highlight: 6, format })        one bar (or [indices]) may carry the accent; dim: [indices]
//   Charts.diverging(el, { labels, up, down, above: 'Sold', below: 'Bought', mark: [3, 9], markLabel: 'Car charged' })
//   Charts.ring(el, { value: 0.72, label: '72%', sub: 'of capacity' }) a progress ring with its total inside
//   Charts.barList(el, [{ label: 'Berlin', value: 412 }, …], { format, thin })  a ranked list where the row is the bar
//   Charts.plan(el, [{ label: 'Groceries', planned: 600, spent: 412, committed: 60 }, …], { scale: 'row' | 'plan' })  planned against spent
//   Charts.bullet(el, [{ label: 'Bonds', value: 0.31, target: 0.25 }, …])   share against a target
//   Charts.timeline(el, rows, kinds, { days, today, weekends })      who is away when, each kind of booking its own mark
//   Charts.matrix(el, rows, { cols, comfort: 2, today })             slack against a minimum, team by day
//   Charts.timeStrip(el, rows, { open: '08:00', close: '15:00', compareLabel: 'Last Sunday' })  when, within the day
// line, bars and diverging take annotations: [{ at: index, label: 'Deploy a3f09c1', short: 'a3f09c1' }] or spans
// [{ from, to, label: 'Cloud' }]. Their labels sit in rows above the plot, measured once the fonts have loaded, and no
// leader line crosses another label; the rows are reserved only when a label exists. reference: { value, label }, its
// label set where no series passes.
// line takes step: true for a balance that only changes on given days; today: index (the forecast after it is dashed)
// with todayLabel: 'Now 20:34' (set clear of the line); endLabel: true (the last value at the line's end); max: caps a
// flat series with one spike (the peak is labelled); yTicks: fixed ticks for a bounded quantity (0–100%); tickFormat:
// axis labels apart from the tooltip format; xAt: the indices to label. Without xAt the x labels keep one step.
// diverging, timeline, matrix and timeStrip return { svg, legend }, and line returns { legend } for two series or more:
// the legend is drawn from the same style objects as the marks, so a swatch is always the mark scaled down. Put it in
// the card's header, or pass legend: element (or a selector) to have it filled.
// Numbers follow the page's language (<html lang>). Every chart gets role="img" and an aria-label that states what it shows.
(() => {
  const NS = 'http://www.w3.org/2000/svg', MINUS = '\u2212', ROW = 14, LANE = (rows) => 8 + rows * ROW + (rows ? 4 : 0);
  const css = (el, name, fb) => getComputedStyle(el).getPropertyValue(name).trim() || fb;
  const cssNum = (el, name, fb) => { const v = parseFloat(css(el, name, '')); return Number.isFinite(v) ? v : fb; };
  const svg = (tag, attrs = {}, parent) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v); if (parent) parent.appendChild(n); return n; };
  const text = (parent, str, attrs) => { const t = svg('text', attrs, parent); t.textContent = str; return t; };
  const titled = (parent, str) => { svg('title', {}, parent).textContent = str; return parent; };
  // numbers follow the page's language (<html lang>), so separators match the rest of the screen
  const nf = (o) => new Intl.NumberFormat(document.documentElement.lang || 'en', o);
  // every text value that reaches innerHTML goes through esc: a label from a database is text, never markup
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const fmt = {
    int: (v) => nf({ maximumFractionDigits: 0 }).format(v),
    dec: (d) => (v) => nf({ minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
    pct: (d = 1) => (v) => nf({ style: 'percent', minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
    money: (cur = 'EUR', d = 0) => (v) => nf({ style: 'currency', currency: cur, minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
    compact: (v) => nf({ notation: 'compact', maximumFractionDigits: 1 }).format(v),
    ms: (v) => `${nf({ maximumFractionDigits: 0 }).format(v)} ms`,
    // a sign on every change, with a true minus: fmt.signed() → '+2', '0', '−1'; fmt.signed(fmt.dec(1)) → '+0.4'
    signed: (f = (v) => nf({ maximumFractionDigits: 0 }).format(v)) => (v) => (v > 0 ? '+' : v < 0 ? MINUS : '') + f(Math.abs(v)),
    // minutes since midnight as a 24-hour time: 680 → '11:20'
    clock: (m) => `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(Math.round(m % 60)).padStart(2, '0')}`, // taste-skill-ignore: a clock, not a counter
  };
  const minutes = (t) => (t == null || t === '' ? null : typeof t === 'number' ? t : (([hh, mm]) => hh * 60 + (mm || 0))(String(t).split(':').map(Number)));
  // Round ticks (steps of 1, 2, 2.5 or 5 × 10^n) whose top sits above the largest value.
  function ticks(min, max, count = 4) {
    if (max === min) max = min + 1;
    const raw = (max - min) / count, mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
    const lo = Math.floor(min / step) * step; let hi = Math.ceil(max / step) * step; if (hi <= max) hi += step;
    const out = []; for (let v = lo; v <= hi + step / 2; v += step) out.push(+v.toFixed(10));
    return out;
  }

  function speech(el, options) {
    function draw() {
      el.replaceChildren();
      const {rows, duration, target, clock, onSelect}=options;
      const w=Math.max(260,el.clientWidth),h=190,p={l:38,r:22,t:12,b:28};
      const s=svg('svg',{viewBox:`0 0 ${w} ${h}`,width:'100%',height:h,role:'img','aria-label':'Mức thoại trước và sau theo thời gian',class:'speech-svg'},el);
      const values=rows.flatMap(r=>[r.before_lufs,r.after_lufs]).filter(Number.isFinite).concat(target);
      const marks=ticks(Math.min(...values)-1,Math.max(...values)+1,4),lo=marks[0],hi=marks.at(-1);
      const x=t=>p.l+t/Math.max(duration,1)*(w-p.l-p.r),y=v=>p.t+(hi-v)/(hi-lo)*(h-p.t-p.b);
      for(const v of marks){svg('line',{x1:p.l,x2:w-p.r,y1:y(v),y2:y(v),class:'chart-grid'},s);text(s,fmt.int(v),{x:p.l-8,y:y(v)+4,'text-anchor':'end',class:'chart-axis'});}
      const count=w<400?3:5;
      for(let i=0;i<count;i++){const t=duration*i/(count-1);text(s,clock(t),{x:x(t),y:h-4,'text-anchor':i===count-1?'end':i===0?'start':'middle',class:'chart-axis'});}
      svg('line',{x1:p.l,x2:w-p.r,y1:y(target),y2:y(target),class:'chart-target'},s);
      for(const row of rows){
        const group=titled(svg('g',{class:row.excluded?'chart-excluded':null},s),`${clock(row.start)}–${clock(row.end)}: ${row.before_lufs ?? '—'} → ${row.after_lufs ?? '—'} LUFS${row.excluded?' · giữ nguyên gain':''}`);
        for(const [key,cls] of [['before_lufs','chart-before'],['after_lufs','chart-after']])if(Number.isFinite(row[key]))svg('line',{x1:x(row.start),x2:Math.max(x(row.start)+1,x(row.end)),y1:y(row[key]),y2:y(row[key]),class:cls},group);
        const hit=svg('rect',{x:x(row.start),y:p.t,width:Math.max(3,x(row.end)-x(row.start)),height:h-p.t-p.b,fill:'transparent',class:'chart-hit'},group);
        hit.addEventListener('click',()=>onSelect(row));
      }
    }
    if(el._speechObserver)el._speechObserver.disconnect();
    el._speechObserver=new ResizeObserver(draw);el._speechObserver.observe(el);draw();
  }
  window.Charts={speech,ticks,fmt};
})();
