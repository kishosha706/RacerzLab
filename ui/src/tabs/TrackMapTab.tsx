import { Crosshair, Info, Layers, Map as MapIcon, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TrackMapIndexEntry, TrackMapOverlayMarker, TrackMapPackage, TrackMapSection } from "../types/trackMap";
import { fetchRunTrackMapPackage, fetchTrackMaps } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";

interface Props {
  runId: string | null; lap?: number | null;
  trackName?: string | null; carName?: string | null; setupName?: string | null;
  targetZoneStartPct?: number; targetZoneEndPct?: number;
}

// ── constants ────────────────────────────────────────────────
type LayerId = "sections"|"target_zone"|"markers"|"all_events"|"front_scrape"|"rear_scrape"|"whole_car_bottoming"|"drag_scrub"|"speed_loss"|"aero"|"shocks"|"delta"|"insights"|"tires"|"notebook";
type HeatmapMode = "normal" | "density" | "severity";
type SeverityLevel = "all" | "critical" | "high" | "watch" | "info";

interface LayerDef { id: LayerId; label: string; group: "map"|"events"|"other"; }

const LAYER_DEFS: LayerDef[] = [
  { id: "sections", label: "Sections", group: "map" },
  { id: "target_zone", label: "Target Zone", group: "map" },
  { id: "markers", label: "Markers", group: "map" },
  { id: "all_events", label: "All Events", group: "events" },
  { id: "front_scrape", label: "Front Scrape", group: "events" },
  { id: "rear_scrape", label: "Rear Scrape", group: "events" },
  { id: "whole_car_bottoming", label: "Bottoming", group: "events" },
  { id: "drag_scrub", label: "Drag/Scrub", group: "events" },
  { id: "speed_loss", label: "Speed Loss", group: "events" },
  { id: "aero", label: "Aero / DP", group: "events" },
  { id: "shocks", label: "Shocks", group: "events" },
  { id: "delta", label: "Delta", group: "other" },
  { id: "insights", label: "Insights", group: "other" },
  { id: "tires", label: "Tires", group: "other" },
  { id: "notebook", label: "Notebook", group: "other" },
];

const CATEGORY_LAYER_MAP: Record<string, LayerId> = {
  front_platform: "front_scrape", rear_platform: "rear_scrape",
  whole_car_bottoming: "whole_car_bottoming", drag_scrub: "drag_scrub",
  speed_loss: "speed_loss", aero_dynamic_pressure: "aero", shocks: "shocks",
};

const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, watch: 2, info: 3 };
const SEVERITY_HEAT_COLORS: Record<string, string> = { critical: "#ef4444", high: "#f97316", watch: "#f59e0b", info: "#38bdf8" };

function classifyOverlayLayer(o: TrackMapOverlayMarker): LayerId {
  // prefer stable category field from backend
  if (o.category) return CATEGORY_LAYER_MAP[o.category] ?? "all_events";
  if (o.kind === "delta_annotation") return "delta";
  if (o.kind === "insight") return "insights";
  if (o.kind === "tire_shock") return "tires";
  if (o.kind === "notebook_finding") return "notebook";
  // fallback label matching
  const l = (o.label || "").toLowerCase();
  if (/whole.?car.?bottoming|bottoming/.test(l)) return "whole_car_bottoming";
  if (/front.?scrape|front.?platform.?low|splitter/.test(l)) return "front_scrape";
  if (/rear.?scrape|rear.?platform.?low|rear.?ride.?height|rear.?contact|min.?rear/.test(l)) return "rear_scrape";
  if (/drag|scrub/.test(l)) return "drag_scrub";
  if (/speed.?loss/.test(l)) return "speed_loss";
  if (/dynamic.?pressure|aero/.test(l)) return "aero";
  if (/shock|damper/.test(l)) return "shocks";
  return "all_events";
}

function severityPasses(s: string|undefined, f: SeverityLevel): boolean {
  if (f === "all" || !s) return true;
  return (SEVERITY_RANK[s]??99) <= (SEVERITY_RANK[f]??0);
}

type CategoryGroup = { category: LayerId; label: string; events: TrackMapOverlayMarker[]; worst: TrackMapOverlayMarker|null };
function groupEventsByCategory(events: TrackMapOverlayMarker[]): CategoryGroup[] {
  const m = new Map<LayerId, TrackMapOverlayMarker[]>();
  for (const e of events) { const c = classifyOverlayLayer(e); if(!m.has(c)) m.set(c,[]); m.get(c)!.push(e); }
  const labels: Record<string,string> = { front_scrape:"Front Platform", rear_scrape:"Rear Platform", whole_car_bottoming:"Whole-Car", drag_scrub:"Drag/Scrub", aero:"Aero", shocks:"Shocks", speed_loss:"Speed Loss", all_events:"Other Events", delta:"Delta", insights:"Insights", tires:"Tires", notebook:"Notebook" };
  return [...m.entries()].map(([c,evts])=>({category:c,label:labels[c]??c,events:evts,worst:evts.reduce((a,b)=>((SEVERITY_RANK[a.severity??"info"]??99)<=(SEVERITY_RANK[b.severity??"info"]??99)?a:b),evts[0])}));
}

type InspectorTarget = { kind:"overlay"; overlay:TrackMapOverlayMarker }|{ kind:"section"; section:TrackMapSection }|{ kind:"none" };

export function TrackMapTab({ runId, lap, trackName, carName, setupName, targetZoneStartPct, targetZoneEndPct }: Props) {
  const [pkg, setPkg] = useState<TrackMapPackage|null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [activeLayers, setActiveLayers] = useState<Set<LayerId>>(()=>new Set(["sections","target_zone","markers","all_events"]));
  const [severityFilter, setSeverityFilter] = useState<SeverityLevel>("all");
  const [heatmap, setHeatmap] = useState<HeatmapMode>("normal");
  const [inspector, setInspector] = useState<InspectorTarget>({kind:"none"});
  const [availableMaps, setAvailableMaps] = useState<TrackMapIndexEntry[]>([]);
  const [mapSearch, setMapSearch] = useState("");
  const [preferredMapId, setPreferredMapId] = useState<string|null>(null);
  const inspectorRef = useRef<HTMLDivElement>(null);
  const { selectSample, selectEvent, selectZone } = useTelemetrySelection();

  useEffect(() => { fetchTrackMaps().then(setAvailableMaps).catch(()=>{}); }, []);
  useEffect(() => {
    if (!runId) { setPkg(null); return; }
    setLoading(true); setError(null);
    fetchRunTrackMapPackage(runId, { lap: lap??undefined, target_zone_start_pct: targetZoneStartPct, target_zone_end_pct: targetZoneEndPct, preferred_map_id: preferredMapId??undefined })
      .then(setPkg).catch((e)=>setError(e instanceof Error?e.message:"Failed to load track map")).finally(()=>setLoading(false));
  }, [runId, lap, targetZoneStartPct, targetZoneEndPct, preferredMapId]);

  const points = pkg?.map?.points ?? [];
  const bounds = pkg?.map?.bounds;
  const overlays = pkg?.overlays ?? [];
  const markers = pkg?.map?.markers ?? [];
  const sections = pkg?.map?.sections ?? [];
  const metadata = pkg?.map?.metadata;
  const match = pkg?.match;

  const handleOverlayClick = useCallback((o: TrackMapOverlayMarker) => {
    setInspector({kind:"overlay",overlay:o});
    if (o.lap_pct!=null) selectSample(0,undefined,o.lap_pct,"track_map");
    if (o.kind==="platform_event"&&o.source_id) selectEvent(o.source_id,"track_map");
    inspectorRef.current?.scrollTo({top:0,behavior:"smooth"});
  }, [selectSample,selectEvent]);
  const handleSectionClick = useCallback((s: TrackMapSection) => { setInspector({kind:"section",section:s}); selectZone(s.section_id); }, [selectZone]);

  // ── computed ──
  const layerCounts = useMemo(() => { const c=new Map<LayerId,number>(); for(const o of overlays){ const cat=classifyOverlayLayer(o); c.set(cat,(c.get(cat)??0)+1); c.set("all_events",(c.get("all_events")??0)+1); } return c; }, [overlays]);
  const visibleOverlays = useMemo(() => overlays.filter(o=>{ const cat=classifyOverlayLayer(o); if(cat==="all_events"&&!activeLayers.has("all_events")){ const el=LAYER_DEFS.filter(d=>d.group==="events"&&d.id!=="all_events").map(d=>d.id); if(!el.some(id=>activeLayers.has(id))) return false; } else if(!activeLayers.has(cat)&&cat!=="all_events") return false; return severityPasses(o.severity,severityFilter); }), [overlays,activeLayers,severityFilter]);
  const selectedHidden = inspector.kind==="overlay" && !visibleOverlays.some(o=>o.marker_id===inspector.overlay.marker_id);

  const sectionStats = useMemo(() => sections.map(s=>{
    const evts=overlays.filter(o=>{if(o.lap_pct==null)return false; return s.wraps_start_finish?o.lap_pct>=s.start_lap_pct||o.lap_pct<=s.end_lap_pct:o.lap_pct>=s.start_lap_pct&&o.lap_pct<=s.end_lap_pct; });
    const worst=evts.reduce((a,b)=>((SEVERITY_RANK[a.severity??"info"]??99)<=(SEVERITY_RANK[b.severity??"info"]??99)?a:b),evts[0]);
    const cats=new Map<string,number>(); for(const e of evts){ const c=classifyOverlayLayer(e); cats.set(c,(cats.get(c)??0)+1); }
    let topCat=""; let topN=0; for(const [k,v] of cats) if(v>topN){ topCat=k; topN=v; }
    return { section:s, count:evts.length, worst, topCat };
  }), [sections, overlays]);

  const analysisSummary = useMemo(() => {
    const ve=visibleOverlays.filter(o=>o.kind==="platform_event");
    if(ve.length===0) return { total:0, worst:null as TrackMapOverlayMarker|null, dominantSection:"", dominantCat:"", sectionsWithEvents:0 };
    const worst=ve.reduce((a,b)=>((SEVERITY_RANK[a.severity??"info"]??99)<=(SEVERITY_RANK[b.severity??"info"]??99)?a:b),ve[0]);
    const secCounts=new Map<string,number>(); for(const o of ve){ const sec=sections.find(s=>{if(!o.lap_pct)return false; return s.wraps_start_finish?o.lap_pct>=s.start_lap_pct||o.lap_pct<=s.end_lap_pct:o.lap_pct>=s.start_lap_pct&&o.lap_pct<=s.end_lap_pct; }); if(sec) secCounts.set(sec.name,(secCounts.get(sec.name)??0)+1); }
    let domSec="", domN=0; for(const [k,v] of secCounts) if(v>domN){ domSec=k; domN=v; }
    const catCounts=new Map<LayerId,number>(); for(const o of ve){ const c=classifyOverlayLayer(o); catCounts.set(c,(catCounts.get(c)??0)+1); }
    let domCat="", domCN=0; for(const [k,v] of catCounts) if(v>domCN){ domCat=k; domCN=v; }
    return { total:ve.length, worst, dominantSection:domSec, dominantCat:domCat, sectionsWithEvents:secCounts.size };
  }, [visibleOverlays, sections]);

  // ── heatmap section color ──
  const sectionColor = useCallback((sp:{count:number, worst:TrackMapOverlayMarker|null}, selected:boolean) => {
    if (heatmap==="density") {
      const maxEvts = Math.max(1, ...sectionStats.map(s=>s.count));
      const t = sp.count/maxEvts;
      return selected ? "#38bdf8" : `rgba(${Math.round(56+180*t)},${Math.round(189-150*t)},${Math.round(248-200*t)},${0.4+0.5*t})`;
    }
    if (heatmap==="severity" && sp.worst) {
      const c = SEVERITY_HEAT_COLORS[sp.worst.severity??"info"] ?? "#8d9aaa";
      return selected ? "#38bdf8" : c;
    }
    return selected ? "#38bdf8" : "#1e40af";
  }, [heatmap, sectionStats]);

  // ── helpers ──
  const toggleLayer = useCallback((id:LayerId)=>setActiveLayers(p=>{const n=new Set(p); n.has(id)?n.delete(id):n.add(id); return n;}),[]);
  const quickAction = useCallback((a:"show_all"|"hide_events"|"platform_only"|"scrape_only")=>setActiveLayers(()=>{const s=new Set<LayerId>(["sections","target_zone","markers"]); if(a==="show_all") for(const d of LAYER_DEFS) s.add(d.id); else if(a==="platform_only") s.add("all_events"); else if(a==="scrape_only") for(const id of ["front_scrape","rear_scrape","whole_car_bottoming"]as LayerId[]) s.add(id); return s;}),[]);
  const setPreferredMap = useCallback((id:string)=>{setPreferredMapId(id); setInspector({kind:"none"});},[]);
  const clearPreferredMap = useCallback(()=>{setPreferredMapId(null); setMapSearch("");},[]);
  const focusSelected = useCallback(()=>{ inspectorRef.current?.scrollIntoView({behavior:"smooth",block:"nearest"}); },[inspectorRef]);

  // ── SVG ──
  const viewBox = useMemo(()=>{ if(!bounds) return"0 0 800 600"; const p=50; return`${bounds.min_x_m-p} ${bounds.min_y_m-p} ${bounds.width_m+p*2} ${bounds.height_m+p*2}`; },[bounds]);
  const pointPath = useMemo(()=>points.length?points.map((p,i)=>`${i===0?"M":"L"} ${p.x??p.x_m} ${p.y??p.y_m}`).join(" "):"",[points]);
  const tzPath = useMemo(()=>{const tz=overlays.find(o=>o.kind==="target_zone"); const pts=tz?.points; if(!pts||pts.length<2)return null; return pts.map((p,i)=>`${i===0?"M":"L"} ${p.x} ${p.y}`).join(" ");},[overlays]);
  const sectionPolylines = useMemo(()=>{ if(!activeLayers.has("sections")||!sections.length)return[]; return sections.map(s=>{ const sp=points.filter(p=>{if(p.lap_pct==null)return false; return s.wraps_start_finish?p.lap_pct>=s.start_lap_pct||p.lap_pct<=s.end_lap_pct:p.lap_pct>=s.start_lap_pct&&p.lap_pct<=s.end_lap_pct;}); const d=sp.map((p,i)=>`${i===0?"M":"L"} ${p.x??p.x_m} ${p.y??p.y_m}`).join(" "); return{section:s,d,count:sp.length}; }).filter(sp=>sp.count>1); },[points,sections,activeLayers]);

  // ── empty states ──
  if (!runId) return <section className="notebook-tab"><h2><MapIcon size={18}/> Track Map</h2><p className="muted">Import a run and .mt2 track map to view spatial data.</p></section>;
  if (loading) return <section className="notebook-tab"><h2><MapIcon size={18}/> Track Map</h2><p className="muted">Loading track map…</p></section>;
  if (error) return <section className="notebook-tab"><h2><MapIcon size={18}/> Track Map</h2><p className="error-text">{error}</p></section>;
  if (!pkg?.map) {
    const filtered = availableMaps.filter(m => !mapSearch || m.display_name.toLowerCase().includes(mapSearch.toLowerCase()));
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18}/> Track Map</h2>
        <div className="notebook-empty">
          <p>No track map matched for this run.</p>
          <p className="muted">Choose a track map manually:</p>
          <div className="trackmap-manual-select">
            <div className="trackmap-search-row">
              <Search size={14} className="muted"/>
              <input className="trackmap-search-input" placeholder="Search maps…" value={mapSearch} onChange={e=>setMapSearch(e.target.value)}/>
            </div>
            {filtered.length>0 ? (
              <select className="trackmap-select" size={Math.min(8,filtered.length)} onChange={e=>setPreferredMap(e.target.value)} defaultValue="">
                <option value="" disabled>Select a track map…</option>
                {filtered.map(m=><option key={m.map_id} value={m.map_id}>{m.display_name} — {m.distance_ft.toFixed(0)} ft</option>)}
              </select>
            ) : <p className="muted">No matches for "{mapSearch}"</p>}
          </div>
        </div>
      </section>
    );
  }

  const selSecId = inspector.kind==="section"?inspector.section.section_id:null;
  const selOvlId = inspector.kind==="overlay"?inspector.overlay.marker_id:null;

  return (
    <section className="trackmap-cockpit">
      <div className="trackmap-left">
        {/* header */}
        <header className="trackmap-header">
          <h2><MapIcon size={18}/> {metadata?.track_name??"Track Map"}</h2>
          <div className="trackmap-header-stats">
            <span className="source-badge source-mt2">.mt2</span>
            {metadata&&<span>{metadata.distance_miles.toFixed(2)} mi · {metadata.distance_ft.toFixed(0)} ft</span>}
            <span>{points.length.toLocaleString()} pts</span><span>{markers.length} mk · {sections.length} sec</span>
          </div>
          <div className="trackmap-header-run">
            {trackName&&<span className="muted">{trackName}</span>}{carName&&<span className="muted">— {carName}</span>}{setupName&&<span className="muted">· {setupName}</span>}
          </div>
          {match&&<div className="trackmap-header-match">
            <span className="map-confidence-badge" data-confidence={match.match_confidence??"medium"}>{match.match_confidence??"medium"}</span>
            <span className="muted">{match.source_filename??match.display_name}</span>
            {lap!=null&&<span className="muted">· Lap {lap}</span>}
            {preferredMapId&&<button className="trackmap-action-btn" onClick={clearPreferredMap} title="Clear manual map"><X size={12}/> Clear</button>}
          </div>}
        </header>

        {/* analysis summary */}
        {analysisSummary.total>0&&<div className="trackmap-summary">
          <span>{analysisSummary.total} visible event{analysisSummary.total!==1?"s":""} across {analysisSummary.sectionsWithEvents} section{analysisSummary.sectionsWithEvents!==1?"s":""}.</span>
          {analysisSummary.worst&&<span> Worst: <span className="event-symbol" style={{color:(analysisSummary.worst as any).color}}>{(analysisSummary.worst as any).symbol} {analysisSummary.worst.label}</span> in {analysisSummary.dominantSection||"unknown"}.</span>}
        </div>}

        {metadata&&!metadata.origin.gps_supported&&<div className="map-warning-banner"><Info size={14}/><span>Centerline-only .mt2 map — no boundaries, banking, GPS, or track width found.</span></div>}

        {/* heatmap mode */}
        <div className="trackmap-mode-row">
          <div className="trackmap-quick-actions">
            <button className={`trackmap-action-btn${heatmap==="normal"?" active":""}`} onClick={()=>setHeatmap("normal")}>Normal</button>
            <button className={`trackmap-action-btn${heatmap==="density"?" active":""}`} onClick={()=>setHeatmap("density")}>Density</button>
            <button className={`trackmap-action-btn${heatmap==="severity"?" active":""}`} onClick={()=>setHeatmap("severity")}>Severity</button>
          </div>
          <button className="trackmap-action-btn" onClick={focusSelected} title="Focus selected"><Crosshair size={12}/> Focus</button>
        </div>

        {/* SVG */}
        <div className="track-map-svg-container">
          <svg viewBox={viewBox} className="track-map-svg">
            <title>Track Map — {metadata?.track_name??"Unknown"}</title>
            <path d={pointPath} fill="none" stroke="#4ade80" strokeWidth={4} strokeOpacity={0.7}/>
            {activeLayers.has("target_zone")&&tzPath&&<path d={tzPath} fill="none" stroke="#22c55e" strokeWidth={8} strokeOpacity={0.4}/>}
            {sectionPolylines.map(sp=>{
              const stat = sectionStats.find(ss=>ss.section.section_id===sp.section.section_id);
              return (<g key={sp.section.section_id} style={{cursor:"pointer"}} onClick={()=>handleSectionClick(sp.section)}>
                <title>{sp.section.name} ({sp.section.section_type}){"\n"}{sp.section.start_lap_pct.toFixed(1)}%–{sp.section.end_lap_pct.toFixed(1)}% · {sp.section.length_ft.toFixed(0)} ft{sp.section.wraps_start_finish?"\nwraps start/finish":""}{stat?`\n${stat.count} events`:"\n0 events"}</title>
                <path d={sp.d} fill="none" stroke={sectionColor({count:stat?.count??0,worst:stat?.worst??null},selSecId===sp.section.section_id)} strokeWidth={selSecId===sp.section.section_id?6:3} strokeOpacity={selSecId===sp.section.section_id?0.9:heatmap==="normal"?0.45:0.7} strokeLinecap="round" strokeLinejoin="round"/>
              </g>);
            })}
            {activeLayers.has("markers")&&markers.map(m=><g key={m.marker_id}><title>{m.name} — {m.distance_ft?.toFixed(0)} ft</title><circle cx={m.x} cy={m.y} r={4} fill="#38bdf8"/><text x={m.x+6} y={m.y-6} fill="#8d9aaa" fontSize={9} fontFamily="Inter, sans-serif">{m.name}</text></g>)}
            {visibleOverlays.filter(o=>o.kind==="platform_event"&&o.x!=null&&o.y!=null).map(o=><g key={o.marker_id} style={{cursor:"pointer"}} onClick={()=>handleOverlayClick(o)}><title>{o.label}{o.description?` — ${o.description}`:""} @ {o.lap_pct?.toFixed(1)}%</title><circle cx={o.x??undefined} cy={o.y??undefined} r={selOvlId===o.marker_id?7:5} fill={o.color??"#f59e0b"} stroke={selOvlId===o.marker_id?"#fff":"#0a0d14"} strokeWidth={selOvlId===o.marker_id?2.5:1.5}/><text x={(o.x??0)+8} y={(o.y??0)+4} fill={o.color??"#f59e0b"} fontSize={9} fontFamily="Inter, sans-serif">{o.symbol??"◆"} {o.label}</text></g>)}
          </svg>
          {visibleOverlays.filter(o=>o.kind==="platform_event").length===0&&overlays.length>0&&<div className="trackmap-empty-map-overlay"><Info size={14}/><span>No visible events for active layers.</span></div>}
        </div>

        {/* mini timeline */}
        <div className="trackmap-timeline">
          <div className="trackmap-timeline-bar">
            {sectionStats.map(s=><div key={s.section.section_id} className="trackmap-timeline-section" style={{left:`${s.section.start_lap_pct}%`,width:`${Math.max(0.5,s.section.end_lap_pct-s.section.start_lap_pct)}%`,background:selSecId===s.section.section_id?"#38bdf8":"#1e293b"}} onClick={()=>handleSectionClick(s.section)} title={`${s.section.name}: ${s.count} event${s.count!==1?"s":""}`}><span className="trackmap-timeline-label">{s.section.name}</span></div>)}
            {visibleOverlays.filter(o=>o.kind==="platform_event"&&o.lap_pct!=null).map(o=><div key={o.marker_id} className={`trackmap-timeline-dot${selOvlId===o.marker_id?" selected":""}`} style={{left:`${o.lap_pct}%`,background:o.color??"#f59e0b"}} onClick={()=>handleOverlayClick(o)} title={`${o.symbol} ${o.label} @ ${o.lap_pct?.toFixed(1)}%`}/>)}
          </div>
          <div className="trackmap-timeline-ticks">
            <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
          </div>
        </div>

        {/* section cards */}
        <div className="trackmap-section-cards">
          <h4>Sections</h4>
          <div className="trackmap-section-cards-grid">
            {sectionStats.slice(0,12).map(s=><div key={s.section.section_id} className={`trackmap-section-card${selSecId===s.section.section_id?" selected":""}`} onClick={()=>handleSectionClick(s.section)}>
              <div className="trackmap-section-card-header">
                <span className="trackmap-section-card-name">{s.section.name}</span>
                <span className="inspector-badge inspector-badge-sm" data-type={s.section.section_type}>{s.section.section_type}</span>
              </div>
              <div className="trackmap-section-card-meta">
                <span>{s.section.start_lap_pct.toFixed(0)}–{s.section.end_lap_pct.toFixed(0)}% · {s.section.length_ft.toFixed(0)} ft</span>
              </div>
              <div className="trackmap-section-card-stats">
                <span>{s.count} event{s.count!==1?"s":""}</span>
                {s.worst&&<span className="inspector-badge inspector-badge-sm" data-severity={s.worst.severity??"info"}>{s.worst.severity}</span>}
                {s.topCat&&<span className="muted">{s.topCat}</span>}
              </div>
            </div>)}
          </div>
        </div>

        {/* fallback events */}
        {visibleOverlays.filter(o=>o.kind==="platform_event"&&o.x==null).length>0&&<div className="map-fallback-events"><h4>Events (lap-distance only)</h4>
          {visibleOverlays.filter(o=>o.kind==="platform_event"&&o.x==null).map(o=><div key={o.marker_id} className="map-event-row" style={{cursor:"pointer"}} onClick={()=>handleOverlayClick(o)}><span className="event-symbol" style={{color:o.color}}>{o.symbol} {o.label}</span><span className="event-pct">@{o.lap_pct?.toFixed(1)}%</span></div>)}
        </div>}

        {/* layers */}
        <div className="trackmap-toggles">
          <div className="trackmap-toggles-header"><h4><Layers size={13}/> Layers</h4>
            <div className="trackmap-quick-actions">
              <button className="trackmap-action-btn" onClick={()=>quickAction("show_all")} title="Show All">All</button>
              <button className="trackmap-action-btn" onClick={()=>quickAction("hide_events")} title="Hide events">Map</button>
              <button className="trackmap-action-btn" onClick={()=>quickAction("platform_only")} title="Platform only">Plat</button>
              <button className="trackmap-action-btn" onClick={()=>quickAction("scrape_only")} title="Scrape only">Scrape</button>
            </div>
          </div>
          <div className="trackmap-toggle-grid">
            {LAYER_DEFS.map(d=>{const count=layerCounts.get(d.id); const hasData=d.group==="map"||(count!=null&&count>0); return<label key={d.id} className={`toggle-label${!hasData?" toggle-disabled":""}`} title={!hasData?"No data for this layer":d.label}><input type="checkbox" checked={activeLayers.has(d.id)} disabled={!hasData} onChange={()=>toggleLayer(d.id)}/>{d.label}{count!=null?` (${count})`:""}</label>;})}
          </div>
          <div className="trackmap-severity-filter"><label className="muted" style={{fontSize:11}}>Severity:</label>
            <select className="trackmap-select trackmap-select-sm" value={severityFilter} onChange={e=>setSeverityFilter(e.target.value as SeverityLevel)}>
              <option value="all">All</option><option value="critical">Critical</option><option value="high">High+</option><option value="watch">Watch+</option><option value="info">Info</option>
            </select>
          </div>
        </div>
      </div>

      {/* ── RIGHT: Inspector ── */}
      <aside className="trackmap-inspector" ref={inspectorRef}>
        {inspector.kind==="none"&&<div className="inspector-empty">
          <Info size={20}/><p>Click a section or event marker to inspect track evidence.</p>
          {!match&&availableMaps.length>0&&<div className="trackmap-manual-select" style={{marginTop:12}}><p className="muted" style={{marginBottom:6}}>Or pick a map manually:</p>
            <select className="trackmap-select" onChange={e=>setPreferredMap(e.target.value)} defaultValue=""><option value="" disabled>Select a track map…</option>{availableMaps.map(m=><option key={m.map_id} value={m.map_id}>{m.display_name}</option>)}</select>
          </div>}
        </div>}

        {/* section inspector */}
        {inspector.kind==="section"&&<div className="inspector-body">
          <h3>{inspector.section.name}</h3>
          <span className="inspector-badge" data-type={inspector.section.section_type}>{inspector.section.section_type}</span>
          <div className="inspector-fields"><div><label>Range</label><span>{inspector.section.start_lap_pct.toFixed(1)}%–{inspector.section.end_lap_pct.toFixed(1)}%</span></div><div><label>Length</label><span>{inspector.section.length_ft.toFixed(0)} ft</span></div>{inspector.section.wraps_start_finish&&<div><label>Wraps</label><span>start/finish line</span></div>}</div>
          {(()=>{const se=overlays.filter(o=>{if(o.lap_pct==null)return false; const s=inspector.section; return s.wraps_start_finish?o.lap_pct>=s.start_lap_pct||o.lap_pct<=s.end_lap_pct:o.lap_pct>=s.start_lap_pct&&o.lap_pct<=s.end_lap_pct;}); if(!se.length)return<p className="muted" style={{marginTop:12}}>No events in this section.</p>; const grps=groupEventsByCategory(se); return<div className="inspector-events"><h4>{se.length} event{se.length!==1?"s":""} in {grps.length} categor{grps.length!==1?"ies":"y"}</h4>{grps.map(g=><div key={g.category} className="inspector-event-group"><div className="inspector-event-group-header"><span className="event-symbol" style={{color:g.worst?.color}}>{g.worst?.symbol??""}</span><span>{g.label}</span><span className="muted">({g.events.length})</span>{g.worst&&<span className="inspector-badge inspector-badge-sm" data-severity={g.worst.severity??"info"}>{g.worst.severity}</span>}</div>{g.events.slice(0,5).map(e=><div key={e.marker_id} className="inspector-event-row" onClick={()=>handleOverlayClick(e)}><span className="event-symbol" style={{color:e.color}}>{e.symbol}</span><span>{e.label}</span><span className="muted">@{e.lap_pct?.toFixed(1)}%</span></div>)}{g.events.length>5&&<p className="muted" style={{fontSize:10,margin:0}}>+{g.events.length-5} more</p>}</div>)}</div>;})()}
          {(()=>{const stat=sectionStats.find(s=>s.section.section_id===inspector.section.section_id); if(!stat||!stat.worst)return null; return<div className="inspector-evidence"><h4>Evidence Stack</h4><div className="inspector-block"><label>Location</label><span>{inspector.section.start_lap_pct.toFixed(1)}%–{inspector.section.end_lap_pct.toFixed(1)}% · {inspector.section.length_ft.toFixed(0)} ft</span></div><div className="inspector-block"><label>Severity</label><span className="inspector-badge inspector-badge-sm" data-severity={stat.worst.severity??"info"}>{stat.worst.severity}</span></div>{stat.count>0&&<div className="inspector-block"><label>Events</label><span>{stat.count} events · worst: {stat.worst.label} @ {stat.worst.lap_pct?.toFixed(1)}%</span></div>}</div>;})()}
        </div>}

        {/* overlay inspector — evidence stack */}
        {inspector.kind==="overlay"&&<div className="inspector-body">
          {selectedHidden&&<div className="map-warning-banner" style={{marginBottom:10}}><Info size={12}/><span>Selected event hidden — adjust layer filters.</span></div>}
          <h3>{inspector.overlay.symbol} {inspector.overlay.label}</h3>
          <div className="inspector-badges">
            <span className="inspector-badge" data-severity={inspector.overlay.severity??"info"}>{inspector.overlay.severity??"info"}</span>
            <span className="inspector-badge">{inspector.overlay.kind}</span>
            {inspector.overlay.confidence&&<span className="inspector-badge">{inspector.overlay.confidence}</span>}
            {inspector.overlay.event_type&&<span className="inspector-badge">{inspector.overlay.event_type}</span>}
          </div>
          {/* Evidence blocks */}
          <div className="inspector-evidence">
            <div className="inspector-block"><label>Location</label><span>{inspector.overlay.lap_pct?.toFixed(2)}%{inspector.overlay.distance_ft!=null?` · ${inspector.overlay.distance_ft.toFixed(0)} ft`:""}{inspector.overlay.heading_rad!=null?` · ${((inspector.overlay.heading_rad*180)/Math.PI).toFixed(1)}°`:""}</span></div>
            <div className="inspector-block"><label>Severity</label><span className="inspector-badge inspector-badge-sm" data-severity={inspector.overlay.severity??"info"}>{inspector.overlay.severity??"info"}</span>{inspector.overlay.confidence&&<span className="muted" style={{marginLeft:6}}>confidence: {inspector.overlay.confidence}</span>}{inspector.overlay.source_type&&<span className="muted" style={{marginLeft:6}}>source: {inspector.overlay.source_type}</span>}</div>
            {inspector.overlay.description&&<div className="inspector-block"><label>Description</label><span>{inspector.overlay.description}</span></div>}
            {(inspector.overlay as any).front_platform_risk_score!=null||(inspector.overlay as any).rear_platform_risk_score!=null||(inspector.overlay as any).whole_car_bottoming_risk!=null?<div className="inspector-block inspector-block-emphasis"><label>Platform Balance</label><div className="inspector-block-content">{(inspector.overlay as any).platform_balance_label&&<span className={`platform-label platform-${String((inspector.overlay as any).platform_balance_label).toLowerCase().replace(/\s+/g,"-")}`}>{(inspector.overlay as any).platform_balance_label}</span>}<div className="inspector-block-grid">{(inspector.overlay as any).front_platform_risk_score!=null&&<span>Front: {(inspector.overlay as any).front_platform_risk_score}</span>}{(inspector.overlay as any).rear_platform_risk_score!=null&&<span>Rear: {(inspector.overlay as any).rear_platform_risk_score}</span>}{(inspector.overlay as any).whole_car_bottoming_risk!=null&&<span className="text-critical">Bottoming: {(inspector.overlay as any).whole_car_bottoming_risk}</span>}{(inspector.overlay as any).rear_scrape_side_label&&<span>Side: {(inspector.overlay as any).rear_scrape_side_label}</span>}</div>{(inspector.overlay as any).platform_balance_explanation&&<p className="muted" style={{fontSize:11,marginTop:4}}>{(inspector.overlay as any).platform_balance_explanation}</p>}</div></div>:<div className="inspector-block" style={{opacity:0.5}}><label>Platform Balance</label><span className="muted">Unavailable</span></div>}
            {inspector.overlay.related_channels&&inspector.overlay.related_channels.length>0&&<div className="inspector-block"><label>Channels</label><div className="channel-chips">{inspector.overlay.related_channels.map(c=><span key={c} className="channel-chip">{c}</span>)}</div></div>}
            {inspector.overlay.source_id&&<div className="inspector-block"><label>Source ID</label><span className="mono">{inspector.overlay.source_id}</span></div>}
          </div>
        </div>}
      </aside>
    </section>
  );
}
