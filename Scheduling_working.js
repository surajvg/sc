
// // // // import React, { Fragment, useEffect, useRef, useState } from "react";
// // // // import axios from "axios";
// // // // import {
// // // //   Alert, Box, Button, Chip, Collapse, FormControlLabel, LinearProgress, MenuItem, Select, Stack, Switch,
// // // //   TextField, Tooltip, Typography,
// // // // } from "@mui/material";

// // // // /* ------------------------------------------------------------------ *
// // // //  *  "PO on Station" grid  (rows = stations, columns = working days)
// // // //  *    blue cell   = one PO worked on that station that day
// // // //  *    orange cell = two or more POs share that station that day
// // // //  *    blank       = idle
// // // //  *
// // // //  *  Backend:  GET {apiBase}/schedule/po-gantt          (see po_gantt_service.py)
// // // //  *            GET {apiBase}/schedule/po-gantt/export   (same params, .xlsx)
// // // //  *  Only needs react, axios and @mui/material.
// // // //  * ------------------------------------------------------------------ */

// // // // const DEFAULT_API = "http://localhost:2002";
// // // // const NAME_W = 200;      // station name column
// // // // const SHIFT_W = 64;      // "2 shift" column
// // // // const ROW_H = 30;
// // // // const HEAD_H = 28;
// // // // const COLORS = { BLUE: "#9fc5e8", ORANGE: "#f6b26b" };
// // // // const HEAD_BG = "#dde3ee";
// // // // const BORDER = "1px solid #c9cfd8";

// // // // const fmtDay = (iso) => {
// // // //   if (!iso) return "";
// // // //   const d = new Date(iso + "T00:00:00");
// // // //   return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }).replace(" ", "-");
// // // // };
// // // // const fmtLong = (iso) =>
// // // //   iso ? new Date(iso + "T00:00:00").toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" }) : "-";

// // // // const buildQuery = ({ pos, startDate, timeSource, labelMode, showHolidays }) => {
// // // //   const q = new URLSearchParams();
// // // //   pos.forEach((p) => q.append("production_order", p));          // repeated param, order = load priority
// // // //   if (startDate) q.append("start_date", startDate);
// // // //   q.append("time_source", timeSource);
// // // //   q.append("label_mode", labelMode);
// // // //   q.append("show_holidays", String(showHolidays));
// // // //   return q.toString();
// // // // };

// // // // const errorText = async (err, fallback) => {
// // // //   try {
// // // //     let data = err.response?.data;
// // // //     if (data instanceof Blob) data = JSON.parse(await data.text());   // export errors arrive as a blob
// // // //     const d = data?.detail;
// // // //     if (typeof d === "string") return d;
// // // //     if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
// // // //   } catch (_) { /* ignore */ }
// // // //   return err.message ? `${fallback} (${err.message})` : fallback;
// // // // };

// // // // /* ------------------------------------------------------------------ *
// // // //  *  The grid itself - exported so it can be reused / tested with plain data
// // // //  * ------------------------------------------------------------------ */
// // // // export function PoGanttGrid({ data, cellW = 78, focus = "", expanded, onToggle }) {
// // // //   const days = data.days || [];
// // // //   const stations = data.stations || [];

// // // //   const stickyHead = (top, extra = {}) => ({
// // // //     position: "sticky", top, zIndex: 3, bgcolor: HEAD_BG, height: HEAD_H, border: BORDER,
// // // //     fontWeight: 700, fontSize: 12, textAlign: "center", whiteSpace: "nowrap", ...extra,
// // // //   });

// // // //   const cellsOf = (row) => {
// // // //     const m = new Map();
// // // //     (row.cells || []).forEach((c) => m.set(c.working_day_no, c));
// // // //     return m;
// // // //   };

// // // //   const dataCell = (row, d, key) => {
// // // //     const cell = cellsOf(row).get(d.working_day_no);
// // // //     const has = !!(cell && cell.pos && cell.pos.length);
// // // //     const dim = !!focus && has && !cell.pos.includes(focus);
// // // //     const pct = has && cell.capacity_minutes > 0 ? Math.round((100 * cell.minutes_used) / cell.capacity_minutes) : null;
// // // //     const bg = has ? COLORS[cell.color] || COLORS.BLUE : d.is_holiday ? "#e5e7eb" : "#fff";
// // // //     const body = (
// // // //       <Box sx={{ px: 0.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600, fontSize: 12 }}>
// // // //         {has ? cell.pos.join(" ") : ""}
// // // //       </Box>
// // // //     );
// // // //     return (
// // // //       <Box
// // // //         component="td" key={key}
// // // //         sx={{ minWidth: cellW, width: cellW, maxWidth: cellW, height: ROW_H, border: BORDER, textAlign: "center", p: 0, bgcolor: bg, opacity: dim ? 0.25 : 1 }}
// // // //       >
// // // //         {has ? (
// // // //           <Tooltip arrow title={
// // // //             <Box sx={{ fontSize: 12 }}>
// // // //               <div><b>{row.name || row.step_name}</b></div>
// // // //               <div>{fmtLong(d.date)} (working day {d.working_day_no})</div>
// // // //               <div>POs: {cell.pos.join(", ")}</div>
// // // //               <div>Used {Math.round(cell.minutes_used)} of {Math.round(cell.capacity_minutes)} min{pct !== null ? ` (${pct}%)` : ""}</div>
// // // //             </Box>
// // // //           }>{body}</Tooltip>
// // // //         ) : body}
// // // //       </Box>
// // // //     );
// // // //   };

// // // //   const labelCells = (st, { member = false, canExpand = false, open = false }) => (
// // // //     <>
// // // //       <Box
// // // //         component="td"
// // // //         sx={{ position: "sticky", left: 0, zIndex: 2, bgcolor: member ? "#f7f9fc" : "#eef2f8", border: BORDER, px: 1, minWidth: NAME_W, width: NAME_W, height: ROW_H }}
// // // //       >
// // // //         <Stack direction="row" alignItems="center" sx={{ gap: 0.5, pl: member ? 2 : 0 }}>
// // // //           {canExpand && (
// // // //             <Box onClick={() => onToggle && onToggle(st.station_id)} sx={{ cursor: "pointer", userSelect: "none", fontSize: 11, width: 14 }}>
// // // //               {open ? "▾" : "▸"}
// // // //             </Box>
// // // //           )}
// // // //           <Box sx={{ minWidth: 0 }}>
// // // //             <Box sx={{ fontWeight: member ? 500 : 700, fontSize: 12, lineHeight: 1.2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
// // // //               {member ? st.step_name : st.name}
// // // //               {canExpand ? <span style={{ fontWeight: 400, color: "#6b7280" }}> ({(st.members || []).length} steps)</span> : null}
// // // //             </Box>
// // // //             {!member && (st.role || st.part_number) && (
// // // //               <Box sx={{ fontSize: 10, color: "#6b7280", lineHeight: 1.1 }}>
// // // //                 {[st.role === "CHILD" ? "Child" : st.role === "MAIN" ? "Main" : "", st.part_number].filter(Boolean).join(" · ")}
// // // //               </Box>
// // // //             )}
// // // //           </Box>
// // // //         </Stack>
// // // //       </Box>
// // // //       <Box
// // // //         component="td"
// // // //         sx={{ position: "sticky", left: NAME_W, zIndex: 2, bgcolor: member ? "#f7f9fc" : "#eef2f8", border: BORDER, textAlign: "center", fontSize: 11, color: "#4b5563", minWidth: SHIFT_W, width: SHIFT_W }}
// // // //       >
// // // //         {!member && st.shifts ? `${st.shifts} shift` : ""}
// // // //       </Box>
// // // //     </>
// // // //   );

// // // //   return (
// // // //     <Box component="table" sx={{ borderCollapse: "separate", borderSpacing: 0, tableLayout: "fixed" }}>
// // // //       <thead>
// // // //         <tr>
// // // //           <Box component="th" colSpan={2} sx={{ ...stickyHead(0, { left: 0, zIndex: 5, textAlign: "left", px: 1 }) }}>Working day #</Box>
// // // //           {days.map((d) => (
// // // //             <Box component="th" key={`n${d.working_day_no}-${d.date}`} sx={stickyHead(0, d.is_holiday ? { bgcolor: "#cfd4dc", color: "#6b7280" } : {})}>
// // // //               {d.is_holiday ? "Off" : d.working_day_no}
// // // //             </Box>
// // // //           ))}
// // // //         </tr>
// // // //         <tr>
// // // //           <Box component="th" colSpan={2} sx={{ ...stickyHead(HEAD_H, { left: 0, zIndex: 5, textAlign: "left", px: 1, fontWeight: 600 }) }}>Date</Box>
// // // //           {days.map((d) => (
// // // //             <Box component="th" key={`d${d.date}`} sx={stickyHead(HEAD_H, { fontWeight: 500, ...(d.is_holiday ? { bgcolor: "#cfd4dc", color: "#6b7280" } : {}) })}>
// // // //               {fmtDay(d.date)}
// // // //             </Box>
// // // //           ))}
// // // //         </tr>
// // // //         <tr>
// // // //           <Box component="th" colSpan={2} sx={{ ...stickyHead(HEAD_H * 2, { left: 0, zIndex: 5, textAlign: "left", px: 1, fontWeight: 600 }) }}>Day</Box>
// // // //           {days.map((d) => (
// // // //             <Box component="th" key={`w${d.date}`} sx={stickyHead(HEAD_H * 2, { fontWeight: 500, ...(d.is_holiday ? { bgcolor: "#cfd4dc", color: "#6b7280" } : {}) })}>
// // // //               {d.weekday}
// // // //             </Box>
// // // //           ))}
// // // //         </tr>
// // // //       </thead>
// // // //       <tbody>
// // // //         <tr>
// // // //           <Box component="td" colSpan={2 + days.length} sx={{ position: "sticky", left: 0, bgcolor: "#eef2f8", border: BORDER, px: 1, fontWeight: 700, fontSize: 12, color: "#1f3864", height: ROW_H }}>
// // // //             PO ON STATION (B# = production order label)
// // // //           </Box>
// // // //         </tr>
// // // //         {stations.map((st) => {
// // // //           const isLine = st.process_mode === "LINE" && (st.members || []).length > 0;
// // // //           const open = !!(expanded && expanded.has(st.station_id));
// // // //           return (
// // // //             <Fragment key={st.station_id}>
// // // //               <tr>
// // // //                 {labelCells(st, { canExpand: isLine, open })}
// // // //                 {days.map((d) => dataCell(st, d, `${st.station_id}-${d.date}`))}
// // // //               </tr>
// // // //               {isLine && open && st.members.map((m, i) => (
// // // //                 <tr key={`${st.station_id}-m${m.flow_step_id ?? i}`}>
// // // //                   {labelCells(m, { member: true })}
// // // //                   {days.map((d) => dataCell(m, d, `${st.station_id}-m${m.flow_step_id ?? i}-${d.date}`))}
// // // //                 </tr>
// // // //               ))}
// // // //             </Fragment>
// // // //           );
// // // //         })}
// // // //       </tbody>
// // // //     </Box>
// // // //   );
// // // // }

// // // // /* ------------------------------------------------------------------ *
// // // //  *  Page
// // // //  * ------------------------------------------------------------------ */
// // // // export default function ScheduleDashboard({ apiBase = DEFAULT_API }) {
// // // //   const [data, setData] = useState(null);
// // // //   const [allPos, setAllPos] = useState([]);            // every yet-to-start PO the backend knows (from the unfiltered load)
// // // //   const [poSel, setPoSel] = useState([]);              // POs to load - click order = load priority
// // // //   const [startDate, setStartDate] = useState("");      // empty = next working day
// // // //   const [timeSource, setTimeSource] = useState("actual");
// // // //   const [labelMode, setLabelMode] = useState("seq");
// // // //   const [showHolidays, setShowHolidays] = useState(false);
// // // //   const [cellW, setCellW] = useState(78);
// // // //   const [focus, setFocus] = useState("");
// // // //   const [expanded, setExpanded] = useState(() => new Set());
// // // //   const [showWarn, setShowWarn] = useState(false);
// // // //   const [showAssume, setShowAssume] = useState(false);
// // // //   const [loading, setLoading] = useState(false);
// // // //   const [exporting, setExporting] = useState(false);
// // // //   const [error, setError] = useState("");
// // // //   const [isFullscreen, setIsFullscreen] = useState(false);
// // // //   const fsRef = useRef(null);

// // // //   const authHeaders = () => ({ "x-access-token": localStorage.getItem("token") || "" });   // read at request time
// // // //   const query = () => buildQuery({ pos: poSel, startDate, timeSource, labelMode, showHolidays });

// // // //   useEffect(() => {
// // // //     const onChange = () => setIsFullscreen(!!document.fullscreenElement);
// // // //     document.addEventListener("fullscreenchange", onChange);
// // // //     return () => document.removeEventListener("fullscreenchange", onChange);
// // // //   }, []);
// // // //   const toggleFullscreen = () => {
// // // //     if (document.fullscreenElement) document.exitFullscreen();
// // // //     else if (fsRef.current) fsRef.current.requestFullscreen();
// // // //   };

// // // //   const generate = async () => {
// // // //     setLoading(true);
// // // //     setError("");
// // // //     try {
// // // //       const res = await axios.get(`${apiBase}/schedule/po-gantt?${query()}`, { headers: authHeaders() });
// // // //       const d = res.data;
// // // //       if (!d?.stations?.length) {
// // // //         setData(null);
// // // //         setError("No yet-to-start production orders could be scheduled.");
// // // //         return;
// // // //       }
// // // //       setData(d);
// // // //       setFocus("");
// // // //       if (!poSel.length) setAllPos(d.meta?.pos || []);       // keep the full list for the PO picker
// // // //     } catch (err) {
// // // //       console.error(err);
// // // //       setData(null);
// // // //       setError(await errorText(err, "Failed to generate the schedule."));
// // // //     } finally {
// // // //       setLoading(false);
// // // //     }
// // // //   };

// // // //   const exportXlsx = async () => {
// // // //     setExporting(true);
// // // //     try {
// // // //       const res = await axios.get(`${apiBase}/schedule/po-gantt/export?${query()}`, { headers: authHeaders(), responseType: "blob" });
// // // //       const url = URL.createObjectURL(res.data);
// // // //       const a = document.createElement("a");
// // // //       a.href = url;
// // // //       a.download = "po_gantt.xlsx";
// // // //       document.body.appendChild(a);
// // // //       a.click();
// // // //       a.remove();
// // // //       URL.revokeObjectURL(url);
// // // //     } catch (err) {
// // // //       setError(await errorText(err, "Export failed."));
// // // //     } finally {
// // // //       setExporting(false);
// // // //     }
// // // //   };

// // // //   const toggleExpand = (id) =>
// // // //     setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

// // // //   const meta = data?.meta;
// // // //   const warnings = data?.warnings || [];
// // // //   const assumptions = data?.assumptions || [];
// // // //   const poOptions = allPos.length ? allPos : meta?.pos || [];

// // // //   return (
// // // //     <Box ref={fsRef} sx={{ p: 2.5, bgcolor: isFullscreen ? "#fff" : "transparent", overflow: "auto", height: isFullscreen ? "100vh" : "auto" }}>
// // // //       <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
// // // //         <Typography variant="h6" sx={{ color: "#333", fontWeight: 600 }}>Production Order Schedule - PO on Station</Typography>
// // // //         <Stack direction="row" sx={{ gap: 1 }}>
// // // //           <Button variant="outlined" onClick={exportXlsx} disabled={!data || exporting}>{exporting ? "Exporting..." : "Export Excel"}</Button>
// // // //           <Button variant="contained" onClick={generate} disabled={loading}>{loading ? "Scheduling..." : "Generate Schedule"}</Button>
// // // //         </Stack>
// // // //       </Stack>

// // // //       {/* inputs */}
// // // //       <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 2 }}>
// // // //         <Select
// // // //           size="small" multiple displayEmpty value={poSel}
// // // //           onChange={(e) => setPoSel(typeof e.target.value === "string" ? e.target.value.split(",") : e.target.value)}
// // // //           renderValue={(sel) => (sel.length ? `${sel.length} PO(s): ${sel.join(", ")}` : "All yet-to-start POs")}
// // // //           sx={{ width: 280 }}
// // // //         >
// // // //           {poOptions.length === 0 && <MenuItem disabled value="">Generate once to list the POs</MenuItem>}
// // // //           {poOptions.map((p) => (
// // // //             <MenuItem key={p.production_order} value={p.production_order}>
// // // //               {p.production_order} - {p.part_number} ({p.quantity})
// // // //             </MenuItem>
// // // //           ))}
// // // //         </Select>
// // // //         <TextField
// // // //           size="small" type="date" label="Start date" InputLabelProps={{ shrink: true }}
// // // //           value={startDate} onChange={(e) => setStartDate(e.target.value)}
// // // //         />
// // // //         <Select size="small" value={timeSource} onChange={(e) => setTimeSource(e.target.value)} sx={{ minWidth: 150 }}>
// // // //           <MenuItem value="actual">Actual time</MenuItem>
// // // //           <MenuItem value="sap">SAP time</MenuItem>
// // // //         </Select>
// // // //         <Select size="small" value={labelMode} onChange={(e) => setLabelMode(e.target.value)} sx={{ minWidth: 150 }}>
// // // //           <MenuItem value="seq">Labels: B1, B2...</MenuItem>
// // // //           <MenuItem value="po">Labels: PO number</MenuItem>
// // // //         </Select>
// // // //         <FormControlLabel
// // // //           control={<Switch size="small" checked={showHolidays} onChange={(e) => setShowHolidays(e.target.checked)} />}
// // // //           label={<span style={{ fontSize: 13 }}>Show off days</span>}
// // // //         />
// // // //         <Button size="small" variant="outlined" onClick={() => setCellW((w) => Math.max(50, w - 10))}>-</Button>
// // // //         <Button size="small" variant="outlined" onClick={() => setCellW((w) => Math.min(140, w + 10))}>+</Button>
// // // //         <Button size="small" variant="outlined" onClick={toggleFullscreen}>{isFullscreen ? "Exit full screen" : "Full screen"}</Button>
// // // //         {poSel.length > 0 && <Button size="small" onClick={() => setPoSel([])}>Load all</Button>}
// // // //       </Stack>
// // // //       <Typography sx={{ fontSize: 12, color: "#6b7280", mb: 1.5 }}>
// // // //         POs are loaded in the order you pick them (first picked = first on the line). Press "Generate Schedule" after changing any input.
// // // //       </Typography>

// // // //       {loading && <LinearProgress sx={{ mb: 1 }} />}
// // // //       {error && <Alert severity="warning" sx={{ mb: 2 }}><b>Notice:</b> {error}</Alert>}

// // // //       {data ? (
// // // //         <>
// // // //           <Box sx={{ bgcolor: "#f6f8fb", borderRadius: "8px", px: 2, py: 1.25, mb: 2, fontSize: 13, color: "#374151" }}>
// // // //             <b>{meta?.number_of_pos ?? meta?.pos?.length ?? 0}</b> PO(s) loaded - {fmtLong(meta?.start_date)} to <b>{fmtLong(meta?.finish_date)}</b> over{" "}
// // // //             <b>{meta?.working_days ?? (data.days || []).filter((d) => !d.is_holiday).length}</b> working day(s).
// // // //           </Box>

// // // //           {warnings.length > 0 && (
// // // //             <Alert severity="warning" sx={{ mb: 2 }}
// // // //               action={<Button color="inherit" size="small" onClick={() => setShowWarn(!showWarn)}>{showWarn ? "Hide" : "Show"}</Button>}>
// // // //               {warnings.length} warning(s)
// // // //               <Collapse in={showWarn}>
// // // //                 <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5, maxHeight: 200, overflow: "auto" }}>
// // // //                   {warnings.map((w, i) => <li key={i}>{w}</li>)}
// // // //                 </Box>
// // // //               </Collapse>
// // // //             </Alert>
// // // //           )}

// // // //           {/* grid */}
// // // //           <Box sx={{ border: "1px solid #ddd", borderRadius: "8px", bgcolor: "#fff", overflow: "auto", maxHeight: isFullscreen ? "calc(100vh - 260px)" : "70vh" }}>
// // // //             <PoGanttGrid data={data} cellW={cellW} focus={focus} expanded={expanded} onToggle={toggleExpand} />
// // // //           </Box>

// // // //           {/* legend */}
// // // //           <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 2, mt: 1.5, fontSize: 12, color: "#374151" }}>
// // // //             <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}><Box sx={{ width: 14, height: 14, bgcolor: COLORS.BLUE, border: BORDER }} />1 PO on the station</Stack>
// // // //             <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}><Box sx={{ width: 14, height: 14, bgcolor: COLORS.ORANGE, border: BORDER }} />2 or more POs share the station</Stack>
// // // //             <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}><Box sx={{ width: 14, height: 14, bgcolor: "#fff", border: BORDER }} />Idle</Stack>
// // // //           </Stack>

// // // //           <Box sx={{ mt: 1.5 }}>
// // // //             <Typography sx={{ fontSize: 12, fontWeight: 700, color: "#374151", mb: 0.5 }}>
// // // //               Production Orders (click one to highlight it)
// // // //             </Typography>
// // // //             <Stack direction="row" flexWrap="wrap" sx={{ gap: 1 }}>
// // // //               {(meta?.pos || []).map((p) => (
// // // //                 <Tooltip key={p.label} arrow title={`${p.part_number}${p.role ? " · " + p.role : ""} · qty ${p.quantity}`}>
// // // //                   <Chip
// // // //                     size="small" label={p.label === p.production_order ? p.label : `${p.label} = ${p.production_order}`}
// // // //                     variant={focus === p.label ? "filled" : "outlined"} color={focus === p.label ? "primary" : "default"}
// // // //                     onClick={() => setFocus(focus === p.label ? "" : p.label)}
// // // //                   />
// // // //                 </Tooltip>
// // // //               ))}
// // // //             </Stack>
// // // //           </Box>

// // // //           {assumptions.length > 0 && (
// // // //             <Box sx={{ mt: 1.5 }}>
// // // //               <Button size="small" onClick={() => setShowAssume(!showAssume)}>{showAssume ? "Hide" : "Show"} assumptions ({assumptions.length})</Button>
// // // //               <Collapse in={showAssume}>
// // // //                 <Box component="ul" sx={{ m: 0, pl: 2.5, fontSize: 12, color: "#4b5563" }}>
// // // //                   {assumptions.map((a, i) => <li key={i}>{a}</li>)}
// // // //                 </Box>
// // // //               </Collapse>
// // // //             </Box>
// // // //           )}

// // // //           <Typography sx={{ fontSize: 12, color: "#6b7280", mt: 1 }}>
// // // //             Each row is a station, each column a working day (Sundays, 1st / 3rd Saturdays and holidays are skipped). Hover a cell for the
// // // //             minutes used. Use the arrow on "SMT Line" to see its individual steps.
// // // //           </Typography>
// // // //         </>
// // // //       ) : (
// // // //         !loading && !error && (
// // // //           <Box sx={{ textAlign: "center", p: 6, color: "#666", bgcolor: "#f8f9fa", borderRadius: "8px" }}>
// // // //             Click "Generate Schedule" to load the yet-to-start production orders onto the stations.
// // // //           </Box>
// // // //         )
// // // //       )}
// // // //     </Box>
// // // //   );
// // // // }





// // // import React, { Fragment, useEffect, useMemo, useRef, useState } from "react";
// // // import axios from "axios";
// // // import {
// // //   Alert, Autocomplete, Box, Button, Chip, Collapse, FormControlLabel, IconButton, LinearProgress, MenuItem,
// // //   Popover, Select, Stack, Switch, TextField, Tooltip, Typography,
// // // } from "@mui/material";
// // // import {
// // //   CalendarMonth as CalendarIcon, ZoomIn as ZoomInIcon, ZoomOut as ZoomOutIcon, OpenInFull as FullscreenIcon,
// // //   FullscreenExit as FullscreenExitIcon, InfoOutlined as InfoIcon, Refresh as RefreshIcon,
// // //   ChevronLeft as PrevIcon, ChevronRight as NextIcon,
// // // } from "@mui/icons-material";

// // // /* ------------------------------------------------------------------ *
// // //  *  "PO on Station" grid  (rows = stations)
// // //  *    columns = HOURS (daily / weekly view), DAYS (monthly view) or MONTHS (yearly view)
// // //  *    blue cell   = one PO worked on that station
// // //  *    orange cell = two or more POs share that station
// // //  *    blank       = idle
// // //  *
// // //  *  Backend:  GET {apiBase}/schedule/po-gantt          (see po_gantt_service.py)
// // //  *            GET {apiBase}/schedule/po-gantt/export   (same params, .xlsx)
// // //  *  Only needs react, axios, @mui/material and @mui/icons-material.
// // //  *
// // //  *  NOTE: the backend returns one cell per station per working day (minutes_used / capacity_minutes).
// // //  *  For the hour-wise columns that day cell is spread over the shift window (SHIFT_START - SHIFT_END),
// // //  *  starting at the shift start, in proportion to minutes_used / capacity_minutes.
// // //  * ------------------------------------------------------------------ */

// // // const DEFAULT_API = "http://localhost:2002";
// // // const NAME_W = 200;      // station name column
// // // const SHIFT_W = 64;      // "2 shift" column
// // // const ROW_H = 30;
// // // const HEAD_H = 28;
// // // const COLORS = { BLUE: "#9fc5e8", ORANGE: "#f6b26b" };
// // // const HEAD_BG = "#dde3ee";
// // // const BORDER = "1px solid #c9cfd8";
// // // const SOFT_BORDER = "#e6e9ef";
// // // const OFF_BG = "#e5e7eb";

// // // /* ---------- view / shift / zoom settings ---------- */
// // // const THEME = {
// // //   primary: "#1f6fe5", info: "#1b9ae1", dark: "#5b6573", border: "#e3e7ee", text: "#1f2937", muted: "#6b7280", nowLine: "#ef4444",
// // // };
// // // const VIEW_MODES = [
// // //   { value: "daily", label: "Daily" },
// // //   { value: "weekly", label: "Weekly" },
// // //   { value: "monthly", label: "Monthly" },
// // //   { value: "yearly", label: "Yearly" },
// // // ];
// // // const SHIFT_START = 6;                 // first hour drawn in the hour-wise columns
// // // const SHIFT_END = 20;                  // end of the last hour drawn (06:00 - 20:00)
// // // const MAX_CUSTOM_RANGE_DAYS = 400;
// // // const ZOOM = { min: 50, max: 140, step: 10, initial: 78 };   // cellW

// // // /* ---------- date helpers ---------- */
// // // const DAY = 24 * 3600 * 1000;
// // // const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
// // // const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// // // const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
// // // const pad = (n) => String(n).padStart(2, "0");
// // // const toDateInput = (ts) => {
// // //   if (!ts) return "";
// // //   const d = new Date(ts);
// // //   return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
// // // };
// // // const fromDateInput = (s) => {
// // //   if (!s) return null;
// // //   const [y, m, d] = s.split("-").map(Number);
// // //   return new Date(y, m - 1, d).getTime();
// // // };
// // // const startOfDay = (ts) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };
// // // const addDays = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n).getTime(); };
// // // const addMonths = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth() + n, 1).getTime(); };
// // // const startOfWeekMon = (ts) => { const d = new Date(startOfDay(ts)); return addDays(d.getTime(), -((d.getDay() + 6) % 7)); };
// // // const fmtShortDate = (ts) => { const d = new Date(ts); return `${pad(d.getDate())} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; };
// // // const dayLabel = (ts) => { const d = new Date(ts); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };

// // // const fmtDay = (iso) => {
// // //   if (!iso) return "";
// // //   const d = new Date(iso + "T00:00:00");
// // //   return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }).replace(" ", "-");
// // // };
// // // const fmtLong = (iso) =>
// // //   iso ? new Date(iso + "T00:00:00").toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" }) : "-";

// // // // anchor = any timestamp inside the period being shown
// // // function getRange(view, anchor, customStart, customEnd) {
// // //   if (customStart && customEnd) {
// // //     const s = startOfDay(Math.min(customStart, customEnd));
// // //     let e = addDays(startOfDay(Math.max(customStart, customEnd)), 1);
// // //     if ((e - s) / DAY > MAX_CUSTOM_RANGE_DAYS) e = addDays(s, MAX_CUSTOM_RANGE_DAYS);
// // //     return { start: s, end: e, custom: true };
// // //   }
// // //   switch (view) {
// // //     case "daily": { const s = startOfDay(anchor); return { start: s, end: addDays(s, 1) }; }
// // //     case "weekly": { const s = startOfWeekMon(anchor); return { start: s, end: addDays(s, 7) }; }
// // //     case "monthly": { const s = addMonths(anchor, 0); return { start: s, end: addMonths(s, 1) }; }
// // //     default: { const s = addMonths(anchor, -1); return { start: s, end: addMonths(s, 12) }; }   // yearly
// // //   }
// // // }
// // // function shiftAnchor(view, anchor, dir, range) {
// // //   if (range?.custom) return anchor;
// // //   switch (view) {
// // //     case "daily": return addDays(anchor, dir);
// // //     case "weekly": return addDays(anchor, 7 * dir);
// // //     case "monthly": return addMonths(anchor, dir);
// // //     default: return addMonths(anchor, 12 * dir);
// // //   }
// // // }

// // // /* ---------- time columns for a view ---------- */
// // // // granularity: daily/weekly -> hours (days if the custom range is > 14 days), monthly -> days (months if > 62 days), yearly -> months
// // // const granularityOf = (view, nDays) => {
// // //   if (view === "yearly") return "month";
// // //   if (view === "monthly") return nDays <= 62 ? "day" : "month";
// // //   return nDays <= 14 ? "hour" : "day";
// // // };

// // // function buildColumns(view, range, dayByDate) {
// // //   const days = [];
// // //   for (let t = range.start; t < range.end; t = addDays(t, 1)) days.push(t);
// // //   const gran = granularityOf(view, days.length);
// // //   const today = toDateInput(Date.now());
// // //   const nowHour = new Date().getHours();
// // //   const dates = Array.from(dayByDate.keys()).sort();
// // //   const first = dates[0], last = dates[dates.length - 1];

// // //   // non-working: a holiday the server sent, a day skipped inside the schedule, or a Sunday outside it
// // //   const isOff = (iso) => {
// // //     const d = dayByDate.get(iso);
// // //     if (d) return !!d.is_holiday;
// // //     if (first && iso > first && iso < last) return true;
// // //     return new Date(iso + "T00:00:00").getDay() === 0;
// // //   };
// // //   const wdText = (iso, off) => (off ? "Off" : dayByDate.get(iso)?.working_day_no ? `WD ${dayByDate.get(iso).working_day_no}` : "");

// // //   const columns = [];
// // //   if (gran === "hour") {
// // //     days.forEach((t) => {
// // //       const iso = toDateInput(t);
// // //       const off = isOff(iso);
// // //       const wd = wdText(iso, off);
// // //       for (let h = SHIFT_START; h < SHIFT_END; h++) {
// // //         columns.push({
// // //           key: `${iso}-${h}`, kind: "hour", date: iso, hour: h, label: `${pad(h)}:00`,
// // //           group: iso, groupLabel: `${dayLabel(t)}${wd ? " · " + wd : ""}`, groupShort: dayLabel(t),
// // //           off, now: iso === today && h === nowHour, groupNow: iso === today,
// // //           dayStart: h === SHIFT_START, dayEnd: h === SHIFT_END - 1,
// // //         });
// // //       }
// // //     });
// // //     return { gran, columns, headLabels: ["Date", "Hour"] };
// // //   }
// // //   if (gran === "day") {
// // //     days.forEach((t) => {
// // //       const d = new Date(t);
// // //       const iso = toDateInput(t);
// // //       const off = isOff(iso);
// // //       columns.push({
// // //         key: iso, kind: "day", date: iso, label: `${d.getDate()} ${WEEKDAYS[d.getDay()][0]}`,
// // //         group: `${d.getFullYear()}-${d.getMonth()}`, groupLabel: `${MONTHS_LONG[d.getMonth()]} ${d.getFullYear()}`, groupShort: MONTHS[d.getMonth()],
// // //         off, now: iso === today, groupNow: false,
// // //       });
// // //     });
// // //     return { gran, columns, headLabels: ["Month", "Day"] };
// // //   }
// // //   // months
// // //   const nowD = new Date();
// // //   for (let t = addMonths(range.start, 0); t < range.end; t = addMonths(t, 1)) {
// // //     const d = new Date(t);
// // //     columns.push({
// // //       key: `${d.getFullYear()}-${pad(d.getMonth() + 1)}`, kind: "month", label: MONTHS[d.getMonth()],
// // //       group: String(d.getFullYear()), groupLabel: String(d.getFullYear()), groupShort: String(d.getFullYear()),
// // //       off: false, now: d.getFullYear() === nowD.getFullYear() && d.getMonth() === nowD.getMonth(), groupNow: false,
// // //     });
// // //   }
// // //   return { gran, columns, headLabels: ["Year", "Month"] };
// // // }

// // // const buildQuery = ({ pos, startDate, timeSource, labelMode, showHolidays }) => {
// // //   const q = new URLSearchParams();
// // //   pos.forEach((p) => q.append("production_order", p));          // repeated param, order = load priority
// // //   if (startDate) q.append("start_date", startDate);
// // //   q.append("time_source", timeSource);
// // //   q.append("label_mode", labelMode);
// // //   q.append("show_holidays", String(showHolidays));
// // //   return q.toString();
// // // };

// // // const errorText = async (err, fallback) => {
// // //   try {
// // //     let data = err.response?.data;
// // //     if (data instanceof Blob) data = JSON.parse(await data.text());   // export errors arrive as a blob
// // //     const d = data?.detail;
// // //     if (typeof d === "string") return d;
// // //     if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
// // //   } catch (_) { /* ignore */ }
// // //   return err.message ? `${fallback} (${err.message})` : fallback;
// // // };

// // // /* ------------------------------------------------------------------ *
// // //  *  Toolbar components
// // //  * ------------------------------------------------------------------ */
// // // const fieldSx = {
// // //   "& .MuiOutlinedInput-root": { borderRadius: "6px", fontSize: 13.5, bgcolor: "#fff", minHeight: 36 },
// // //   "& .MuiOutlinedInput-notchedOutline": { borderColor: THEME.border },
// // // };

// // // /* Daily / Weekly / Monthly / Yearly */
// // // export const ViewSelect = ({ value, onChange }) => (
// // //   <Select size="small" value={value} onChange={(e) => onChange(e.target.value)}
// // //     sx={{ width: 118, height: 36, fontSize: 13.5, borderRadius: "6px", bgcolor: "#fff", "& .MuiOutlinedInput-notchedOutline": { borderColor: THEME.border } }}>
// // //     {VIEW_MODES.map((v) => <MenuItem key={v.value} value={v.value} sx={{ fontSize: 13.5 }}>{v.label}</MenuItem>)}
// // //   </Select>
// // // );

// // // /* "Start Date - End Date" with calendar button */
// // // export const DateRangeField = ({ start, end, onChange }) => {
// // //   const [anchorEl, setAnchorEl] = useState(null);
// // //   const [s, setS] = useState("");
// // //   const [e, setE] = useState("");
// // //   const open = (ev) => { setS(toDateInput(start)); setE(toDateInput(end)); setAnchorEl(ev.currentTarget.closest("[data-daterange]")); };
// // //   const text = start && end ? `${fmtShortDate(start)} – ${fmtShortDate(end)}` : "";

// // //   return (
// // //     <>
// // //       <Box data-daterange sx={{ display: "flex", width: 262 }}>
// // //         <TextField size="small" placeholder="Start Date – End Date" value={text} onClick={open} fullWidth
// // //           InputProps={{ readOnly: true, sx: { cursor: "pointer", borderTopRightRadius: 0, borderBottomRightRadius: 0 } }}
// // //           sx={{ ...fieldSx, "& input": { cursor: "pointer" } }} />
// // //         <IconButton aria-label="Pick dates" onClick={open}
// // //           sx={{ width: 38, height: 36, borderRadius: "0 6px 6px 0", bgcolor: THEME.primary, color: "#fff", "&:hover": { bgcolor: "#1a5fc7" } }}>
// // //           <CalendarIcon fontSize="small" />
// // //         </IconButton>
// // //       </Box>
// // //       <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={() => setAnchorEl(null)} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
// // //         <Stack spacing={1.5} sx={{ p: 2, width: 260 }}>
// // //           <TextField size="small" type="date" label="Start Date" value={s} onChange={(ev) => setS(ev.target.value)} InputLabelProps={{ shrink: true }} />
// // //           <TextField size="small" type="date" label="End Date" value={e} onChange={(ev) => setE(ev.target.value)} InputLabelProps={{ shrink: true }} />
// // //           <Stack direction="row" spacing={1} justifyContent="flex-end">
// // //             <Button size="small" onClick={() => { onChange(null, null); setAnchorEl(null); }}>Clear</Button>
// // //             <Button size="small" variant="contained" disabled={!s || !e}
// // //               onClick={() => { onChange(fromDateInput(s), fromDateInput(e)); setAnchorEl(null); }}>Apply</Button>
// // //           </Stack>
// // //         </Stack>
// // //       </Popover>
// // //     </>
// // //   );
// // // };

// // // /* multi / single select (Autocomplete) */
// // // export const MultiSelect = ({ placeholder, options, value, onChange, width = 200, getLabel = (o) => o }) => (
// // //   <Autocomplete multiple size="small" limitTags={1} disableCloseOnSelect options={options} value={value}
// // //     getOptionLabel={getLabel} onChange={(_, v) => onChange(v)} sx={{ width, ...fieldSx }}
// // //     ChipProps={{ size: "small", sx: { maxWidth: 96, fontSize: 12 } }}
// // //     renderInput={(params) => <TextField {...params} placeholder={value.length ? "" : placeholder} />} />
// // // );

// // // export const SingleSelect = ({ placeholder, options, value, onChange, width = 200, getLabel = (o) => o }) => (
// // //   <Autocomplete size="small" options={options} value={value} getOptionLabel={getLabel} onChange={(_, v) => onChange(v)}
// // //     sx={{ width, ...fieldSx }} renderInput={(params) => <TextField {...params} placeholder={placeholder} />} />
// // // );

// // // /* zoom / fullscreen / info */
// // // const toolSx = { width: 34, height: 34, color: THEME.primary, "&:hover": { bgcolor: "#eef3fb" } };

// // // export const ChartTools = ({ zoomIn, zoomOut, isFullscreen, toggleFullscreen, onInfo }) => (
// // //   <Stack direction="row" spacing={0.5} alignItems="center">
// // //     <Tooltip title="Zoom in"><IconButton aria-label="Zoom in" onClick={zoomIn} sx={toolSx}><ZoomInIcon fontSize="small" /></IconButton></Tooltip>
// // //     <Tooltip title="Zoom out"><IconButton aria-label="Zoom out" onClick={zoomOut} sx={toolSx}><ZoomOutIcon fontSize="small" /></IconButton></Tooltip>
// // //     <Tooltip title={isFullscreen ? "Exit full screen" : "Full screen"}>
// // //       <IconButton aria-label="Full screen" onClick={toggleFullscreen} sx={toolSx}>
// // //         {isFullscreen ? <FullscreenExitIcon fontSize="small" /> : <FullscreenIcon fontSize="small" />}
// // //       </IconButton>
// // //     </Tooltip>
// // //     {onInfo && (
// // //       <Tooltip title="How to use">
// // //         <IconButton aria-label="Info" onClick={onInfo} sx={{ width: 36, height: 36, borderRadius: "6px", bgcolor: THEME.info, color: "#fff", "&:hover": { bgcolor: "#1488c9" } }}>
// // //           <InfoIcon fontSize="small" />
// // //         </IconButton>
// // //       </Tooltip>
// // //     )}
// // //   </Stack>
// // // );

// // // export const InfoPopover = ({ anchorEl, onClose }) => (
// // //   <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}>
// // //     <Box sx={{ p: 2, width: 330, fontSize: 13, color: THEME.text }}>
// // //       <Typography fontWeight={700} fontSize={14} mb={1}>How to read this chart</Typography>
// // //       <Box component="ul" sx={{ m: 0, pl: 2.25, "& li": { mb: 0.5 } }}>
// // //         <li>Each row is a station; each coloured block is the PO (B# label) worked on it.</li>
// // //         <li>Hover a block for the PO(s), date / hour and the minutes used out of the capacity.</li>
// // //         <li><b>Daily</b> and <b>Weekly</b> show hour columns ({pad(SHIFT_START)}:00 - {pad(SHIFT_END)}:00), <b>Monthly</b> shows one column per day and <b>Yearly</b> one per month.</li>
// // //         <li>Use the &lt; &gt; arrows to move period, or pick a start / end date. Zoom stretches the columns.</li>
// // //         <li>Shaded columns are Sundays / holidays; the red underline marks today / the current hour.</li>
// // //         <li>Filter by station or pick a PO to highlight it; the other POs fade.</li>
// // //       </Box>
// // //       <Typography fontWeight={700} fontSize={13} mt={1.5} mb={0.75}>Cell colour</Typography>
// // //       {[[COLORS.BLUE, "1 PO on the station"], [COLORS.ORANGE, "2 or more POs share the station"], ["#fff", "Idle"], [OFF_BG, "Non-working day"]].map(([c, t]) => (
// // //         <Box key={t} sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
// // //           <Box sx={{ width: 26, height: 12, borderRadius: "2px", bgcolor: c, border: BORDER }} />
// // //           <span>{t}</span>
// // //         </Box>
// // //       ))}
// // //     </Box>
// // //   </Popover>
// // // );

// // // export const RefreshButton = ({ onClick, loading }) => (
// // //   <Button variant="contained" startIcon={<RefreshIcon />} onClick={onClick} disabled={loading}
// // //     sx={{ height: 36, width: "8rem", textTransform: "none", fontWeight: 600, fontSize: 13.5, boxShadow: "none", bgcolor: THEME.primary, "&:hover": { bgcolor: "#1a5fc7", boxShadow: "none" } }}>
// // //     Refresh
// // //   </Button>
// // // );

// // // export const ClearFiltersButton = ({ onClick }) => (
// // //   <Button variant="contained" onClick={onClick}
// // //     sx={{ height: 36, width: "8rem", textTransform: "none", fontWeight: 600, fontSize: 13.5, boxShadow: "none", bgcolor: THEME.dark, "&:hover": { bgcolor: "#4a5361", boxShadow: "none" } }}>
// // //     Clear Filters
// // //   </Button>
// // // );

// // // /* ------------------------------------------------------------------ *
// // //  *  The grid itself - exported so it can be reused / tested with plain data
// // //  *
// // //  *  Without `columns` it draws one column per working day (the original layout).
// // //  *  With `columns` (see buildColumns) it draws hour / day / month columns instead;
// // //  *  `cellW` is then the width of ONE column.
// // //  * ------------------------------------------------------------------ */
// // // export function PoGanttGrid({ data, cellW = 78, focus = "", expanded, onToggle, columns, headLabels = ["Date", "Hour"] }) {
// // //   const days = data.days || [];
// // //   const stations = data.stations || [];
// // //   const colMode = Array.isArray(columns) && columns.length > 0;

// // //   const ctx = useMemo(() => {
// // //     const dayByDate = new Map();
// // //     const monthDays = new Map();
// // //     (data.days || []).forEach((d) => {
// // //       dayByDate.set(d.date, d);
// // //       const k = d.date.slice(0, 7);
// // //       if (!monthDays.has(k)) monthDays.set(k, []);
// // //       monthDays.get(k).push(d);
// // //     });
// // //     return { dayByDate, monthDays, rowCache: new WeakMap() };
// // //   }, [data.days]);

// // //   const stickyHead = (top, extra = {}) => ({
// // //     position: "sticky", top, zIndex: 3, bgcolor: HEAD_BG, height: HEAD_H, border: BORDER,
// // //     fontWeight: 700, fontSize: 12, textAlign: "center", whiteSpace: "nowrap", ...extra,
// // //   });

// // //   const cellsOf = (row) => {
// // //     let m = ctx.rowCache.get(row);
// // //     if (!m) {
// // //       m = new Map();
// // //       (row.cells || []).forEach((c) => m.set(c.working_day_no, c));
// // //       ctx.rowCache.set(row, m);
// // //     }
// // //     return m;
// // //   };

// // //   // the cell of one row in one time column (null = idle)
// // //   const resolve = (row, col) => {
// // //     const cm = cellsOf(row);
// // //     const usable = (c) => c && c.pos && c.pos.length;
// // //     if (col.kind === "month") {
// // //       const pos = new Set();
// // //       let used = 0, cap = 0, orange = false;
// // //       (ctx.monthDays.get(col.key) || []).forEach((day) => {
// // //         if (day.is_holiday) return;
// // //         const c = cm.get(day.working_day_no);
// // //         if (!usable(c)) return;
// // //         c.pos.forEach((p) => pos.add(p));
// // //         used += c.minutes_used || 0;
// // //         cap += c.capacity_minutes || 0;
// // //         if (c.color === "ORANGE") orange = true;
// // //       });
// // //       if (!pos.size) return null;
// // //       return { pos: Array.from(pos), color: orange ? "ORANGE" : "BLUE", minutes_used: used, capacity_minutes: cap, fill: 1, label: true };
// // //     }
// // //     const day = ctx.dayByDate.get(col.date);
// // //     if (!day || day.is_holiday) return null;
// // //     const c = cm.get(day.working_day_no);
// // //     if (!usable(c)) return null;
// // //     if (col.kind === "day") return { ...c, fill: 1, label: true };
// // //     // hour column: spread the day's minutes over the shift window, from the shift start
// // //     const hoursN = SHIFT_END - SHIFT_START;
// // //     const f = c.capacity_minutes > 0 ? Math.min(1, c.minutes_used / c.capacity_minutes) : 1;
// // //     const i = col.hour - SHIFT_START;
// // //     const fill = Math.min(1, Math.max(0, f * hoursN - i));
// // //     return fill > 0 ? { ...c, fill, label: i === 0 } : null;
// // //   };

// // //   const whenText = (col, d) => {
// // //     if (!col) return `${fmtLong(d.date)} (working day ${d.working_day_no})`;
// // //     if (col.kind === "hour") return `${fmtLong(col.date)} · ${pad(col.hour)}:00 - ${pad(col.hour + 1)}:00`;
// // //     if (col.kind === "day") return fmtLong(col.date);
// // //     const [y, m] = col.key.split("-").map(Number);
// // //     return `${MONTHS_LONG[m - 1]} ${y}`;
// // //   };

// // //   const dataCell = (row, d, key, col) => {
// // //     const cell = col ? resolve(row, col) : cellsOf(row).get(d.working_day_no);
// // //     const has = !!(cell && cell.pos && cell.pos.length);
// // //     const dim = !!focus && has && !cell.pos.includes(focus);
// // //     const pct = has && cell.capacity_minutes > 0 ? Math.round((100 * cell.minutes_used) / cell.capacity_minutes) : null;
// // //     const color = has ? COLORS[cell.color] || COLORS.BLUE : null;
// // //     const off = col ? col.off : d.is_holiday;
// // //     const fill = has ? (cell.fill ?? 1) : 0;
// // //     const bg = has ? (fill >= 1 ? color : `linear-gradient(to right, ${color} ${fill * 100}%, #fff ${fill * 100}%)`) : off ? OFF_BG : "#fff";
// // //     const isHour = col?.kind === "hour";
// // //     const showLabel = has && (!isHour || cell.label);
// // //     const body = (
// // //       <Box sx={{
// // //         px: 0.5, fontWeight: 600, fontSize: 12, whiteSpace: "nowrap",
// // //         ...(isHour ? { position: "relative", zIndex: 1, textAlign: "left", overflow: "visible" } : { overflow: "hidden", textOverflow: "ellipsis" }),
// // //       }}>
// // //         {showLabel ? cell.pos.join(" ") : ""}
// // //       </Box>
// // //     );
// // //     const borderSx = isHour ? {
// // //       borderLeftColor: col.dayStart ? "#c9cfd8" : SOFT_BORDER,
// // //       borderRightColor: col.dayEnd ? "#c9cfd8" : SOFT_BORDER,
// // //     } : {};
// // //     return (
// // //       <Box
// // //         component="td" key={key}
// // //         sx={{
// // //           minWidth: cellW, width: cellW, maxWidth: cellW, height: ROW_H, border: BORDER, ...borderSx, textAlign: "center", p: 0,
// // //           background: bg, opacity: dim ? 0.25 : 1, overflow: isHour ? "visible" : undefined,
// // //         }}
// // //       >
// // //         {has ? (
// // //           <Tooltip arrow title={
// // //             <Box sx={{ fontSize: 12 }}>
// // //               <div><b>{row.name || row.step_name}</b></div>
// // //               <div>{whenText(col, d)}</div>
// // //               <div>POs: {cell.pos.join(", ")}</div>
// // //               <div>Used {Math.round(cell.minutes_used)} of {Math.round(cell.capacity_minutes)} min{pct !== null ? ` (${pct}%)` : ""}{col && col.kind !== "day" ? (col.kind === "hour" ? " that day" : " in the month") : ""}</div>
// // //             </Box>
// // //           }>{body}</Tooltip>
// // //         ) : body}
// // //       </Box>
// // //     );
// // //   };

// // //   const labelCells = (st, { member = false, canExpand = false, open = false }) => (
// // //     <>
// // //       <Box
// // //         component="td"
// // //         sx={{ position: "sticky", left: 0, zIndex: 2, bgcolor: member ? "#f7f9fc" : "#eef2f8", border: BORDER, px: 1, minWidth: NAME_W, width: NAME_W, height: ROW_H }}
// // //       >
// // //         <Stack direction="row" alignItems="center" sx={{ gap: 0.5, pl: member ? 2 : 0 }}>
// // //           {canExpand && (
// // //             <Box onClick={() => onToggle && onToggle(st.station_id)} sx={{ cursor: "pointer", userSelect: "none", fontSize: 11, width: 14 }}>
// // //               {open ? "▾" : "▸"}
// // //             </Box>
// // //           )}
// // //           <Box sx={{ minWidth: 0 }}>
// // //             <Box sx={{ fontWeight: member ? 500 : 700, fontSize: 12, lineHeight: 1.2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
// // //               {member ? st.step_name : st.name}
// // //               {canExpand ? <span style={{ fontWeight: 400, color: "#6b7280" }}> ({(st.members || []).length} steps)</span> : null}
// // //             </Box>
// // //             {!member && (st.role || st.part_number) && (
// // //               <Box sx={{ fontSize: 10, color: "#6b7280", lineHeight: 1.1 }}>
// // //                 {[st.role === "CHILD" ? "Child" : st.role === "MAIN" ? "Main" : "", st.part_number].filter(Boolean).join(" · ")}
// // //               </Box>
// // //             )}
// // //           </Box>
// // //         </Stack>
// // //       </Box>
// // //       <Box
// // //         component="td"
// // //         sx={{ position: "sticky", left: NAME_W, zIndex: 2, bgcolor: member ? "#f7f9fc" : "#eef2f8", border: BORDER, textAlign: "center", fontSize: 11, color: "#4b5563", minWidth: SHIFT_W, width: SHIFT_W }}
// // //       >
// // //         {!member && st.shifts ? `${st.shifts} shift` : ""}
// // //       </Box>
// // //     </>
// // //   );

// // //   /* ---- header ---- */
// // //   const nowSx = { boxShadow: `inset 0 -2px 0 ${THEME.nowLine}` };
// // //   const offSx = { bgcolor: "#cfd4dc", color: "#6b7280" };

// // //   const groups = [];
// // //   if (colMode) {
// // //     columns.forEach((c) => {
// // //       const g = groups[groups.length - 1];
// // //       if (g && g.key === c.group) { g.n += 1; g.off = g.off && c.off; } else groups.push({ key: c.group, n: 1, label: c.groupLabel, short: c.groupShort, off: c.off, now: c.groupNow });
// // //     });
// // //   }

// // //   const header = colMode ? (
// // //     <thead>
// // //       <tr>
// // //         <Box component="th" colSpan={2} sx={{ ...stickyHead(0, { left: 0, zIndex: 5, textAlign: "left", px: 1 }) }}>{headLabels[0]}</Box>
// // //         {groups.map((g) => (
// // //           <Box component="th" colSpan={g.n} key={`g${g.key}`}
// // //             sx={stickyHead(0, { overflow: "hidden", ...(g.off && columns[0].kind === "hour" ? offSx : {}), ...(g.now ? nowSx : {}) })}>
// // //             {g.n * cellW >= 150 ? g.label : g.short}
// // //           </Box>
// // //         ))}
// // //       </tr>
// // //       <tr>
// // //         <Box component="th" colSpan={2} sx={{ ...stickyHead(HEAD_H, { left: 0, zIndex: 5, textAlign: "left", px: 1, fontWeight: 600 }) }}>{headLabels[1]}</Box>
// // //         {columns.map((c) => (
// // //           <Box component="th" key={`h${c.key}`}
// // //             sx={stickyHead(HEAD_H, { fontWeight: 500, fontSize: c.kind === "hour" ? 11 : 12, ...(c.off ? offSx : {}), ...(c.now ? nowSx : {}) })}>
// // //             {c.kind === "hour" && cellW < 46 ? c.label.slice(0, 2) : c.label}
// // //           </Box>
// // //         ))}
// // //       </tr>
// // //     </thead>
// // //   ) : (
// // //     <thead>
// // //       <tr>
// // //         <Box component="th" colSpan={2} sx={{ ...stickyHead(0, { left: 0, zIndex: 5, textAlign: "left", px: 1 }) }}>Working day #</Box>
// // //         {days.map((d) => (
// // //           <Box component="th" key={`n${d.working_day_no}-${d.date}`} sx={stickyHead(0, d.is_holiday ? offSx : {})}>
// // //             {d.is_holiday ? "Off" : d.working_day_no}
// // //           </Box>
// // //         ))}
// // //       </tr>
// // //       <tr>
// // //         <Box component="th" colSpan={2} sx={{ ...stickyHead(HEAD_H, { left: 0, zIndex: 5, textAlign: "left", px: 1, fontWeight: 600 }) }}>Date</Box>
// // //         {days.map((d) => (
// // //           <Box component="th" key={`d${d.date}`} sx={stickyHead(HEAD_H, { fontWeight: 500, ...(d.is_holiday ? offSx : {}) })}>
// // //             {fmtDay(d.date)}
// // //           </Box>
// // //         ))}
// // //       </tr>
// // //       <tr>
// // //         <Box component="th" colSpan={2} sx={{ ...stickyHead(HEAD_H * 2, { left: 0, zIndex: 5, textAlign: "left", px: 1, fontWeight: 600 }) }}>Day</Box>
// // //         {days.map((d) => (
// // //           <Box component="th" key={`w${d.date}`} sx={stickyHead(HEAD_H * 2, { fontWeight: 500, ...(d.is_holiday ? offSx : {}) })}>
// // //             {d.weekday}
// // //           </Box>
// // //         ))}
// // //       </tr>
// // //     </thead>
// // //   );

// // //   const cols = colMode ? columns : days;
// // //   const cellsFor = (row, keyPrefix) =>
// // //     colMode
// // //       ? columns.map((c) => dataCell(row, null, `${keyPrefix}-${c.key}`, c))
// // //       : days.map((d) => dataCell(row, d, `${keyPrefix}-${d.date}`, null));

// // //   return (
// // //     <Box component="table" sx={{ borderCollapse: "separate", borderSpacing: 0, tableLayout: "fixed" }}>
// // //       {header}
// // //       <tbody>
// // //         <tr>
// // //           <Box component="td" colSpan={2 + cols.length} sx={{ position: "sticky", left: 0, bgcolor: "#eef2f8", border: BORDER, px: 1, fontWeight: 700, fontSize: 12, color: "#1f3864", height: ROW_H }}>
// // //             PO ON STATION (B# = production order label)
// // //           </Box>
// // //         </tr>
// // //         {stations.map((st) => {
// // //           const isLine = st.process_mode === "LINE" && (st.members || []).length > 0;
// // //           const open = !!(expanded && expanded.has(st.station_id));
// // //           return (
// // //             <Fragment key={st.station_id}>
// // //               <tr>
// // //                 {labelCells(st, { canExpand: isLine, open })}
// // //                 {cellsFor(st, `${st.station_id}`)}
// // //               </tr>
// // //               {isLine && open && st.members.map((m, i) => (
// // //                 <tr key={`${st.station_id}-m${m.flow_step_id ?? i}`}>
// // //                   {labelCells(m, { member: true })}
// // //                   {cellsFor(m, `${st.station_id}-m${m.flow_step_id ?? i}`)}
// // //                 </tr>
// // //               ))}
// // //             </Fragment>
// // //           );
// // //         })}
// // //       </tbody>
// // //     </Box>
// // //   );
// // // }

// // // /* ------------------------------------------------------------------ *
// // //  *  Page
// // //  * ------------------------------------------------------------------ */
// // // export default function ScheduleDashboard({ apiBase = DEFAULT_API }) {
// // //   const [data, setData] = useState(null);
// // //   const [allPos, setAllPos] = useState([]);            // every yet-to-start PO the backend knows (from the unfiltered load)
// // //   const [poSel, setPoSel] = useState([]);              // POs to load - click order = load priority
// // //   const [startDate, setStartDate] = useState("");      // empty = next working day
// // //   const [timeSource, setTimeSource] = useState("actual");
// // //   const [labelMode, setLabelMode] = useState("seq");
// // //   const [showHolidays, setShowHolidays] = useState(false);
// // //   const [cellW, setCellW] = useState(ZOOM.initial);
// // //   const [focus, setFocus] = useState("");
// // //   const [expanded, setExpanded] = useState(() => new Set());
// // //   const [showWarn, setShowWarn] = useState(false);
// // //   const [showAssume, setShowAssume] = useState(false);
// // //   const [loading, setLoading] = useState(false);
// // //   const [exporting, setExporting] = useState(false);
// // //   const [error, setError] = useState("");
// // //   const [isFullscreen, setIsFullscreen] = useState(false);
// // //   const fsRef = useRef(null);

// // //   /* view / filter state */
// // //   const [view, setView] = useState("weekly");
// // //   const [anchor, setAnchor] = useState(() => Date.now());
// // //   const [customStart, setCustomStart] = useState(null);
// // //   const [customEnd, setCustomEnd] = useState(null);
// // //   const [stationSel, setStationSel] = useState([]);
// // //   const [infoAnchor, setInfoAnchor] = useState(null);
// // //   const [gridEl, setGridEl] = useState(null);
// // //   const [gridW, setGridW] = useState(0);

// // //   const authHeaders = () => ({ "x-access-token": localStorage.getItem("token") || "" });   // read at request time
// // //   const query = () => buildQuery({ pos: poSel, startDate, timeSource, labelMode, showHolidays });

// // //   useEffect(() => {
// // //     const onChange = () => setIsFullscreen(!!document.fullscreenElement);
// // //     document.addEventListener("fullscreenchange", onChange);
// // //     return () => document.removeEventListener("fullscreenchange", onChange);
// // //   }, []);
// // //   const toggleFullscreen = () => {
// // //     if (document.fullscreenElement) document.exitFullscreen();
// // //     else if (fsRef.current) fsRef.current.requestFullscreen();
// // //   };

// // //   // keep the width of the grid area so short views (daily / yearly) stretch to fill it
// // //   useEffect(() => {
// // //     if (!gridEl) return undefined;
// // //     setGridW(gridEl.clientWidth);
// // //     if (typeof ResizeObserver === "undefined") return undefined;
// // //     const ro = new ResizeObserver((entries) => setGridW(entries[0].contentRect.width));
// // //     ro.observe(gridEl);
// // //     return () => ro.disconnect();
// // //   }, [gridEl]);

// // //   const generate = async () => {
// // //     setLoading(true);
// // //     setError("");
// // //     try {
// // //       const res = await axios.get(`${apiBase}/schedule/po-gantt?${query()}`, { headers: authHeaders() });
// // //       const d = res.data;
// // //       if (!d?.stations?.length) {
// // //         setData(null);
// // //         setError("No yet-to-start production orders could be scheduled.");
// // //         return;
// // //       }
// // //       const first = d.meta?.start_date || d.days?.[0]?.date;
// // //       if (first && first !== (data?.meta?.start_date || data?.days?.[0]?.date)) {   // new schedule start -> show it
// // //         setAnchor(fromDateInput(first));
// // //         setCustomStart(null);
// // //         setCustomEnd(null);
// // //       }
// // //       setData(d);
// // //       setFocus("");
// // //       setStationSel([]);
// // //       if (!poSel.length) setAllPos(d.meta?.pos || []);       // keep the full list for the PO picker
// // //     } catch (err) {
// // //       console.error(err);
// // //       setData(null);
// // //       setError(await errorText(err, "Failed to generate the schedule."));
// // //     } finally {
// // //       setLoading(false);
// // //     }
// // //   };

// // //   const exportXlsx = async () => {
// // //     setExporting(true);
// // //     try {
// // //       const res = await axios.get(`${apiBase}/schedule/po-gantt/export?${query()}`, { headers: authHeaders(), responseType: "blob" });
// // //       const url = URL.createObjectURL(res.data);
// // //       const a = document.createElement("a");
// // //       a.href = url;
// // //       a.download = "po_gantt.xlsx";
// // //       document.body.appendChild(a);
// // //       a.click();
// // //       a.remove();
// // //       URL.revokeObjectURL(url);
// // //     } catch (err) {
// // //       setError(await errorText(err, "Export failed."));
// // //     } finally {
// // //       setExporting(false);
// // //     }
// // //   };

// // //   const toggleExpand = (id) =>
// // //     setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

// // //   /* ---- view controls ---- */
// // //   const scheduleStart = () => {
// // //     const first = data?.meta?.start_date || data?.days?.[0]?.date;
// // //     return first ? fromDateInput(first) : Date.now();
// // //   };
// // //   const changeView = (v) => { setView(v); setCustomStart(null); setCustomEnd(null); setCellW(ZOOM.initial); };
// // //   const range = useMemo(() => getRange(view, anchor, customStart, customEnd), [view, anchor, customStart, customEnd]);
// // //   const navigate = (dir) => setAnchor((a) => shiftAnchor(view, a, dir, range));
// // //   const zoomIn = () => setCellW((w) => Math.min(ZOOM.max, w + ZOOM.step));
// // //   const zoomOut = () => setCellW((w) => Math.max(ZOOM.min, w - ZOOM.step));
// // //   const clearFilters = () => {
// // //     setStationSel([]);
// // //     setFocus("");
// // //     setCustomStart(null);
// // //     setCustomEnd(null);
// // //     setCellW(ZOOM.initial);
// // //     setAnchor(scheduleStart());
// // //   };

// // //   const meta = data?.meta;
// // //   const warnings = data?.warnings || [];
// // //   const assumptions = data?.assumptions || [];
// // //   const poOptions = allPos.length ? allPos : meta?.pos || [];

// // //   const dayByDate = useMemo(() => {
// // //     const m = new Map();
// // //     (data?.days || []).forEach((d) => m.set(d.date, d));
// // //     return m;
// // //   }, [data]);

// // //   const { gran, columns, headLabels } = useMemo(() => buildColumns(view, range, dayByDate), [view, range, dayByDate]);

// // //   const colW = useMemo(() => {
// // //     const base = gran === "hour" ? Math.round(cellW * 0.45) : gran === "day" ? Math.round(cellW * 0.6) : Math.round(cellW * 1.1);
// // //     const avail = Math.max(0, gridW - NAME_W - SHIFT_W - 4);
// // //     return Math.max(base, Math.floor(avail / Math.max(columns.length, 1)));
// // //   }, [gran, cellW, gridW, columns.length]);

// // //   const stationOptions = useMemo(() => Array.from(new Set((data?.stations || []).map((s) => s.name))), [data]);
// // //   const gridData = useMemo(() => {
// // //     if (!data) return null;
// // //     if (!stationSel.length) return data;
// // //     return { ...data, stations: (data.stations || []).filter((s) => stationSel.includes(s.name)) };
// // //   }, [data, stationSel]);

// // //   const poLabelText = (label) => {
// // //     const p = (meta?.pos || []).find((x) => x.label === label);
// // //     return p && p.label !== p.production_order ? `${p.label} = ${p.production_order}` : label;
// // //   };

// // //   const rangeEndInclusive = addDays(range.end, -1);
// // //   const hasWorkInRange = useMemo(() => {
// // //     const a = toDateInput(range.start), b = toDateInput(rangeEndInclusive);
// // //     return (data?.days || []).some((d) => !d.is_holiday && d.date >= a && d.date <= b);
// // //   }, [data, range, rangeEndInclusive]);

// // //   const periodText = `${fmtShortDate(range.start)}${range.end - range.start > DAY ? ` – ${fmtShortDate(rangeEndInclusive)}` : ""}`;
// // //   const granText = gran === "hour" ? "hour-wise" : gran === "day" ? "day-wise" : "month-wise";

// // //   return (
// // //     <Box ref={fsRef} sx={{ p: 2.5, bgcolor: isFullscreen ? "#fff" : "transparent", overflow: "auto", height: isFullscreen ? "100vh" : "auto" }}>
// // //       <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
// // //         <Typography variant="h6" sx={{ color: "#333", fontWeight: 600 }}>Production Order Schedule - PO on Station</Typography>
// // //         <Stack direction="row" sx={{ gap: 1 }}>
// // //           <Button variant="outlined" onClick={exportXlsx} disabled={!data || exporting}>{exporting ? "Exporting..." : "Export Excel"}</Button>
// // //           <Button variant="contained" onClick={generate} disabled={loading}>{loading ? "Scheduling..." : "Generate Schedule"}</Button>
// // //         </Stack>
// // //       </Stack>

// // //       {/* inputs */}
// // //       <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 2 }}>
// // //         <Select
// // //           size="small" multiple displayEmpty value={poSel}
// // //           onChange={(e) => setPoSel(typeof e.target.value === "string" ? e.target.value.split(",") : e.target.value)}
// // //           renderValue={(sel) => (sel.length ? `${sel.length} PO(s): ${sel.join(", ")}` : "All yet-to-start POs")}
// // //           sx={{ width: 280 }}
// // //         >
// // //           {poOptions.length === 0 && <MenuItem disabled value="">Generate once to list the POs</MenuItem>}
// // //           {poOptions.map((p) => (
// // //             <MenuItem key={p.production_order} value={p.production_order}>
// // //               {p.production_order} - {p.part_number} ({p.quantity})
// // //             </MenuItem>
// // //           ))}
// // //         </Select>
// // //         <TextField
// // //           size="small" type="date" label="Start date" InputLabelProps={{ shrink: true }}
// // //           value={startDate} onChange={(e) => setStartDate(e.target.value)}
// // //         />
// // //         <Select size="small" value={timeSource} onChange={(e) => setTimeSource(e.target.value)} sx={{ minWidth: 150 }}>
// // //           <MenuItem value="actual">Actual time</MenuItem>
// // //           <MenuItem value="sap">SAP time</MenuItem>
// // //         </Select>
// // //         <Select size="small" value={labelMode} onChange={(e) => setLabelMode(e.target.value)} sx={{ minWidth: 150 }}>
// // //           <MenuItem value="seq">Labels: B1, B2...</MenuItem>
// // //           <MenuItem value="po">Labels: PO number</MenuItem>
// // //         </Select>
// // //         <FormControlLabel
// // //           control={<Switch size="small" checked={showHolidays} onChange={(e) => setShowHolidays(e.target.checked)} />}
// // //           label={<span style={{ fontSize: 13 }}>Show off days</span>}
// // //         />
// // //         {poSel.length > 0 && <Button size="small" onClick={() => setPoSel([])}>Load all</Button>}
// // //       </Stack>
// // //       <Typography sx={{ fontSize: 12, color: "#6b7280", mb: 1.5 }}>
// // //         POs are loaded in the order you pick them (first picked = first on the line). Press "Generate Schedule" after changing any input.
// // //       </Typography>

// // //       {/* view / filter toolbar */}
// // //       <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 2 }}>
// // //         <ViewSelect value={view} onChange={changeView} />
// // //         <Stack direction="row" alignItems="center">
// // //           <Tooltip title="Previous"><span><IconButton aria-label="Previous" size="small" disabled={!!range.custom} onClick={() => navigate(-1)} sx={toolSx}><PrevIcon fontSize="small" /></IconButton></span></Tooltip>
// // //           <Tooltip title="Next"><span><IconButton aria-label="Next" size="small" disabled={!!range.custom} onClick={() => navigate(1)} sx={toolSx}><NextIcon fontSize="small" /></IconButton></span></Tooltip>
// // //         </Stack>
// // //         <DateRangeField
// // //           start={customStart || range.start} end={customEnd || rangeEndInclusive}
// // //           onChange={(s, e) => { setCustomStart(s); setCustomEnd(e); }}
// // //         />
// // //         <MultiSelect placeholder="All stations" options={stationOptions} value={stationSel} onChange={setStationSel} width={230} />
// // //         <SingleSelect
// // //           placeholder="Highlight PO" options={(meta?.pos || []).map((p) => p.label)} value={focus || null}
// // //           onChange={(v) => setFocus(v || "")} getLabel={poLabelText} width={200}
// // //         />
// // //         <ChartTools
// // //           zoomIn={zoomIn} zoomOut={zoomOut} isFullscreen={isFullscreen} toggleFullscreen={toggleFullscreen}
// // //           onInfo={(e) => setInfoAnchor(e.currentTarget)}
// // //         />
// // //         <ClearFiltersButton onClick={clearFilters} />
// // //         <RefreshButton onClick={generate} loading={loading} />
// // //       </Stack>
// // //       <InfoPopover anchorEl={infoAnchor} onClose={() => setInfoAnchor(null)} />

// // //       {loading && <LinearProgress sx={{ mb: 1 }} />}
// // //       {error && <Alert severity="warning" sx={{ mb: 2 }}><b>Notice:</b> {error}</Alert>}

// // //       {data ? (
// // //         <>
// // //           <Box sx={{ bgcolor: "#f6f8fb", borderRadius: "8px", px: 2, py: 1.25, mb: 2, fontSize: 13, color: "#374151" }}>
// // //             <b>{meta?.number_of_pos ?? meta?.pos?.length ?? 0}</b> PO(s) loaded - {fmtLong(meta?.start_date)} to <b>{fmtLong(meta?.finish_date)}</b> over{" "}
// // //             <b>{meta?.working_days ?? (data.days || []).filter((d) => !d.is_holiday).length}</b> working day(s).
// // //             <Box component="span" sx={{ ml: 1.5, color: THEME.muted }}>Showing {periodText} ({granText})</Box>
// // //           </Box>

// // //           {warnings.length > 0 && (
// // //             <Alert severity="warning" sx={{ mb: 2 }}
// // //               action={<Button color="inherit" size="small" onClick={() => setShowWarn(!showWarn)}>{showWarn ? "Hide" : "Show"}</Button>}>
// // //               {warnings.length} warning(s)
// // //               <Collapse in={showWarn}>
// // //                 <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5, maxHeight: 200, overflow: "auto" }}>
// // //                   {warnings.map((w, i) => <li key={i}>{w}</li>)}
// // //                 </Box>
// // //               </Collapse>
// // //             </Alert>
// // //           )}

// // //           {!hasWorkInRange && (
// // //             <Alert severity="info" sx={{ mb: 2 }}
// // //               action={<Button color="inherit" size="small" onClick={clearFilters}>Go to schedule start</Button>}>
// // //               No scheduled work in this period.
// // //             </Alert>
// // //           )}

// // //           {/* grid */}
// // //           <Box ref={setGridEl} sx={{ border: "1px solid #ddd", borderRadius: "8px", bgcolor: "#fff", overflow: "auto", maxHeight: isFullscreen ? "calc(100vh - 320px)" : "70vh" }}>
// // //             <PoGanttGrid data={gridData} cellW={colW} focus={focus} expanded={expanded} onToggle={toggleExpand} columns={columns} headLabels={headLabels} />
// // //           </Box>

// // //           {/* legend */}
// // //           <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 2, mt: 1.5, fontSize: 12, color: "#374151" }}>
// // //             <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}><Box sx={{ width: 14, height: 14, bgcolor: COLORS.BLUE, border: BORDER }} />1 PO on the station</Stack>
// // //             <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}><Box sx={{ width: 14, height: 14, bgcolor: COLORS.ORANGE, border: BORDER }} />2 or more POs share the station</Stack>
// // //             <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}><Box sx={{ width: 14, height: 14, bgcolor: "#fff", border: BORDER }} />Idle</Stack>
// // //             <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}><Box sx={{ width: 14, height: 14, bgcolor: OFF_BG, border: BORDER }} />Non-working day</Stack>
// // //           </Stack>

// // //           <Box sx={{ mt: 1.5 }}>
// // //             <Typography sx={{ fontSize: 12, fontWeight: 700, color: "#374151", mb: 0.5 }}>
// // //               Production Orders (click one to highlight it)
// // //             </Typography>
// // //             <Stack direction="row" flexWrap="wrap" sx={{ gap: 1 }}>
// // //               {(meta?.pos || []).map((p) => (
// // //                 <Tooltip key={p.label} arrow title={`${p.part_number}${p.role ? " · " + p.role : ""} · qty ${p.quantity}`}>
// // //                   <Chip
// // //                     size="small" label={p.label === p.production_order ? p.label : `${p.label} = ${p.production_order}`}
// // //                     variant={focus === p.label ? "filled" : "outlined"} color={focus === p.label ? "primary" : "default"}
// // //                     onClick={() => setFocus(focus === p.label ? "" : p.label)}
// // //                   />
// // //                 </Tooltip>
// // //               ))}
// // //             </Stack>
// // //           </Box>

// // //           {assumptions.length > 0 && (
// // //             <Box sx={{ mt: 1.5 }}>
// // //               <Button size="small" onClick={() => setShowAssume(!showAssume)}>{showAssume ? "Hide" : "Show"} assumptions ({assumptions.length})</Button>
// // //               <Collapse in={showAssume}>
// // //                 <Box component="ul" sx={{ m: 0, pl: 2.5, fontSize: 12, color: "#4b5563" }}>
// // //                   {assumptions.map((a, i) => <li key={i}>{a}</li>)}
// // //                 </Box>
// // //               </Collapse>
// // //             </Box>
// // //           )}

// // //           <Typography sx={{ fontSize: 12, color: "#6b7280", mt: 1 }}>
// // //             Each row is a station. Daily / Weekly show one column per hour ({pad(SHIFT_START)}:00 - {pad(SHIFT_END)}:00), Monthly one per day and Yearly one per month
// // //             (Sundays, 1st / 3rd Saturdays and holidays are skipped). Hover a block for the minutes used. Use the arrow on "SMT Line" to see its individual steps.
// // //           </Typography>
// // //         </>
// // //       ) : (
// // //         !loading && !error && (
// // //           <Box sx={{ textAlign: "center", p: 6, color: "#666", bgcolor: "#f8f9fa", borderRadius: "8px" }}>
// // //             Click "Generate Schedule" to load the yet-to-start production orders onto the stations.
// // //           </Box>
// // //         )
// // //       )}
// // //     </Box>
// // //   );
// // // }



// // import React, { useEffect, useMemo, useRef, useState } from "react";
// // import axios from "axios";
// // // import axios from "../../AxiosInstance/axiosInstance";
// // // import fetch from "../../AxiosInstance/fecthInstance"
// // import {
// //   Alert, Autocomplete, Box, Button, Collapse, FormControlLabel, IconButton, LinearProgress, MenuItem,
// //   Popover, Select, Stack, Switch, TextField, Tooltip, Typography,
// // } from "@mui/material";
// // import {
// //   CalendarMonth as CalendarIcon, ZoomIn as ZoomInIcon, ZoomOut as ZoomOutIcon, OpenInFull as FullscreenIcon,
// //   FullscreenExit as FullscreenExitIcon, InfoOutlined as InfoIcon, Refresh as RefreshIcon,
// //   ChevronLeft as PrevIcon, ChevronRight as NextIcon,
// // } from "@mui/icons-material";

// // /* ------------------------------------------------------------------ *
// //  *  "PO on Station" Gantt   (rows = stations, bars = POs, one colour per PO)
// //  *
// //  *  Backend:  GET {apiBase}/schedule/po-gantt          (see po_gantt_service.py)
// //  *            GET {apiBase}/schedule/po-gantt/export   (same params, .xlsx)
// //  *  Only needs react, axios, @mui/material and @mui/icons-material.
// //  *
// //  *  The backend sends one cell per station per working day (pos, minutes_used, capacity_minutes).
// //  *  The bars are drawn inside the shift window (SHIFT_START - SHIFT_END) of that day, starting at the
// //  *  shift start; the day's used share (minutes_used / capacity_minutes) is split equally between its POs.
// //  * ------------------------------------------------------------------ */

// // const DEFAULT_API = "http://localhost:2002";

// // /* ---------- constants (from the schedule config) ---------- */
// // const PO_PALETTE = [
// //   "#1e88e5", "#f59e0b", "#10b981", "#e11d48", "#8b5cf6", "#14b8a6",
// //   "#f97316", "#84cc16", "#ec4899", "#0ea5e9", "#a16207", "#6366f1",
// // ];
// // const VIEW_MODES = [
// //   { value: "daily", label: "Daily" },
// //   { value: "weekly", label: "Weekly" },
// //   { value: "monthly", label: "Monthly" },
// //   { value: "yearly", label: "Yearly" },
// // ];
// // const THEME = {
// //   primary: "#1f6fe5", info: "#1b9ae1", dark: "#5b6573", border: "#e3e7ee", gridStrong: "#c9d0da", gridSoft: "#eceff4",
// //   text: "#1f2937", muted: "#6b7280", nowLine: "#ef4444", offDay: "rgba(100,116,139,0.10)", headBg: "#f4f6fa",
// // };
// // const LAYOUT = { labelWidth: 270, headerRow1: 30, headerRow2: 28, barPad: 4, laneHeight: 34 };
// // const ROW_H = LAYOUT.laneHeight + 2 * LAYOUT.barPad;
// // const BASE_DAY_WIDTH = { daily: 900, weekly: 156, monthly: 46, yearly: 3.2 };   // px per day at zoom = 1
// // const ZOOM = { min: 0.5, max: 6, step: 0.5 };
// // const MAX_CUSTOM_RANGE_DAYS = 400;
// // const SHIFT_START = 6;   // first hour drawn in daily / weekly view
// // const SHIFT_END = 20;    // last hour drawn (06:00 - 20:00)

// // /* ---------- date helpers ---------- */
// // const DAY = 24 * 3600 * 1000;
// // const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
// // const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// // const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
// // const pad = (n) => String(n).padStart(2, "0");
// // const toDateInput = (ts) => {
// //   if (!ts) return "";
// //   const d = new Date(ts);
// //   return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
// // };
// // const fromDateInput = (s) => {
// //   if (!s) return null;
// //   const [y, m, d] = s.split("-").map(Number);
// //   return new Date(y, m - 1, d).getTime();
// // };
// // const startOfDay = (ts) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };
// // const addDays = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n).getTime(); };
// // const addMonths = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth() + n, 1).getTime(); };
// // const startOfWeekMon = (ts) => { const d = new Date(startOfDay(ts)); return addDays(d.getTime(), -((d.getDay() + 6) % 7)); };
// // const fmtShortDate = (ts) => { const d = new Date(ts); return `${pad(d.getDate())} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; };
// // const fmtLong = (iso) =>
// //   iso ? new Date(iso + "T00:00:00").toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" }) : "-";
// // const dayLabel = (ts) => { const d = new Date(ts); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
// // const hm = (ts) => { const d = new Date(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

// // // anchor = any timestamp inside the period being shown
// // function getRange(view, anchor, customStart, customEnd) {
// //   if (customStart && customEnd) {
// //     const s = startOfDay(Math.min(customStart, customEnd));
// //     let e = addDays(startOfDay(Math.max(customStart, customEnd)), 1);
// //     if ((e - s) / DAY > MAX_CUSTOM_RANGE_DAYS) e = addDays(s, MAX_CUSTOM_RANGE_DAYS);
// //     return { start: s, end: e, custom: true };
// //   }
// //   switch (view) {
// //     case "daily": { const s = startOfDay(anchor); return { start: s, end: addDays(s, 1) }; }
// //     case "weekly": { const s = startOfWeekMon(anchor); return { start: s, end: addDays(s, 7) }; }
// //     case "monthly": { const s = addMonths(anchor, 0); return { start: s, end: addMonths(s, 1) }; }
// //     default: { const s = addMonths(anchor, -1); return { start: s, end: addMonths(s, 12) }; }   // yearly
// //   }
// // }
// // function shiftAnchor(view, anchor, dir, range) {
// //   if (range?.custom) return anchor;
// //   switch (view) {
// //     case "daily": return addDays(anchor, dir);
// //     case "weekly": return addDays(anchor, 7 * dir);
// //     case "monthly": return addMonths(anchor, dir);
// //     default: return addMonths(anchor, 12 * dir);
// //   }
// // }

// // /* ---------- the time axis ----------
// //  * Daily / Weekly draw only the working window of each day (06:00-20:00) with a label for the hours;
// //  * Monthly / Yearly draw the full 24 h.  toX converts a timestamp to a pixel x inside the timeline. */
// // function buildScale({ view, range, zoom, availableWidth, isOff, wdText }) {
// //   const windowed = view === "daily" || view === "weekly";
// //   const wStart = windowed ? SHIFT_START : 0;
// //   const wEnd = windowed ? SHIFT_END : 24;
// //   const hours = wEnd - wStart;

// //   const days = [];
// //   for (let t = range.start; t < range.end; t = addDays(t, 1)) days.push(t);

// //   let baseDay = BASE_DAY_WIDTH[view] || 100;
// //   if (view === "daily" && days.length > 1) baseDay = BASE_DAY_WIDTH.weekly;
// //   const fill = Math.max(0, availableWidth) / Math.max(days.length, 1);
// //   const dayW = Math.max(baseDay, fill) * zoom;
// //   const totalWidth = dayW * days.length;
// //   const winStart = (i) => days[i] + wStart * 3600e3;
// //   const winLen = hours * 3600e3;

// //   const dayIndexOf = (ts) => {
// //     if (ts <= days[0]) return -1;
// //     let lo = 0, hi = days.length - 1;
// //     while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (days[mid] <= ts) lo = mid; else hi = mid - 1; }
// //     return ts >= range.end ? days.length : lo;
// //   };
// //   const toX = (ts) => {
// //     const i = dayIndexOf(ts);
// //     if (i < 0) return 0;
// //     if (i >= days.length) return totalWidth;
// //     const frac = Math.min(1, Math.max(0, (ts - winStart(i)) / winLen));
// //     return i * dayW + frac * dayW;
// //   };

// //   const row1 = [], row2 = [], grid = [];
// //   const groupBy = (keyFn, labelFn, target) => {
// //     let startIdx = 0;
// //     for (let i = 1; i <= days.length; i++) {
// //       if (i === days.length || keyFn(days[i]) !== keyFn(days[startIdx])) {
// //         target.push({ x: startIdx * dayW, w: (i - startIdx) * dayW, label: labelFn(days[startIdx], i - startIdx) });
// //         startIdx = i;
// //       }
// //     }
// //   };
// //   const hourPx = dayW / hours;

// //   if (windowed) {
// //     days.forEach((d, i) => {
// //       const dt = new Date(d);
// //       const wd = wdText(toDateInput(d));
// //       row1.push({
// //         x: i * dayW, w: dayW, off: isOff(toDateInput(d)),
// //         label: dayW >= 170 ? `${dayLabel(d)}${wd ? " · " + wd : ""}` : dayW >= 90 ? dayLabel(d) : String(dt.getDate()),
// //       });
// //       const step = [1, 2, 3, 4, 6, 12].find((s) => s * hourPx >= 46) || hours;      // hour labels never overlap
// //       for (let h = wStart; h < wEnd; h += step) {
// //         const next = Math.min(h + step, wEnd);
// //         row2.push({ x: i * dayW + ((h - wStart) / hours) * dayW, w: ((next - h) / hours) * dayW, label: `${pad(h)}:00` });
// //       }
// //       if (hourPx >= 6 && days.length <= 31) for (let h = wStart + 1; h < wEnd; h++) grid.push({ x: i * dayW + ((h - wStart) / hours) * dayW, strong: false });
// //     });
// //   } else if (view === "monthly") {
// //     groupBy((t) => `${new Date(t).getFullYear()}-${new Date(t).getMonth()}`, (t) => `${MONTHS_LONG[new Date(t).getMonth()]} ${new Date(t).getFullYear()}`, row1);
// //     days.forEach((d, i) => row2.push({ x: i * dayW, w: dayW, label: String(new Date(d).getDate()), sub: WEEKDAYS[new Date(d).getDay()][0], off: isOff(toDateInput(d)) }));
// //   } else {
// //     groupBy((t) => new Date(t).getFullYear(), (t) => String(new Date(t).getFullYear()), row1);
// //     groupBy((t) => `${new Date(t).getFullYear()}-${new Date(t).getMonth()}`, (t, n) => (n * dayW < 30 ? MONTHS[new Date(t).getMonth()][0] : MONTHS[new Date(t).getMonth()]), row2);
// //   }
// //   if (!windowed) row2.forEach((c) => grid.push({ x: c.x, strong: false }));
// //   row1.forEach((c) => grid.push({ x: c.x, strong: true }));

// //   const offDays = [];
// //   if (dayW >= 12) days.forEach((d, i) => { if (isOff(toDateInput(d))) offDays.push({ x: i * dayW, w: dayW }); });

// //   return { days, dayW, totalWidth, toX, row1, row2, grid, offDays, windowed, wStart, wEnd };
// // }

// // /* ---------- misc ---------- */
// // const buildQuery = ({ pos, startDate, timeSource, labelMode, showHolidays }) => {
// //   const q = new URLSearchParams();
// //   pos.forEach((p) => q.append("production_order", p));          // repeated param, order = load priority
// //   if (startDate) q.append("start_date", startDate);
// //   q.append("time_source", timeSource);
// //   q.append("label_mode", labelMode);
// //   q.append("show_holidays", String(showHolidays));
// //   return q.toString();
// // };

// // const errorText = async (err, fallback) => {
// //   try {
// //     let data = err.response?.data;
// //     if (data instanceof Blob) data = JSON.parse(await data.text());   // export errors arrive as a blob
// //     const d = data?.detail;
// //     if (typeof d === "string") return d;
// //     if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
// //   } catch (_) { /* ignore */ }
// //   return err.message ? `${fallback} (${err.message})` : fallback;
// // };

// // // one colour per PO label (first colour = blue, used when a single PO is shown)
// // export function buildColorMap(data) {
// //   const labels = (data?.meta?.pos || []).map((p) => p.label);
// //   const seen = new Set(labels);
// //   const rows = (data?.stations || []).flatMap((s) => [s, ...(s.members || [])]);
// //   rows.forEach((r) => (r.cells || []).forEach((c) => (c.pos || []).forEach((p) => { if (!seen.has(p)) { seen.add(p); labels.push(p); } })));
// //   const map = {};
// //   labels.forEach((l, i) => { map[l] = PO_PALETTE[i % PO_PALETTE.length]; });
// //   return map;
// // }

// // /* ------------------------------------------------------------------ *
// //  *  Toolbar components
// //  * ------------------------------------------------------------------ */
// // const fieldSx = {
// //   "& .MuiOutlinedInput-root": { borderRadius: "6px", fontSize: 13.5, bgcolor: "#fff", minHeight: 36 },
// //   "& .MuiOutlinedInput-notchedOutline": { borderColor: THEME.border },
// // };
// // const selectSx = { height: 36, fontSize: 13.5, borderRadius: "6px", bgcolor: "#fff", "& .MuiOutlinedInput-notchedOutline": { borderColor: THEME.border } };
// // const toolSx = { width: 34, height: 34, color: THEME.primary, "&:hover": { bgcolor: "#eef3fb" } };
// // const btnSx = { height: 36, textTransform: "none", fontWeight: 600, fontSize: 13.5, boxShadow: "none", whiteSpace: "nowrap" };

// // /* Weekly / Daily / Monthly / Yearly */
// // export const ViewSelect = ({ value, onChange }) => (
// //   <Select size="small" value={value} onChange={(e) => onChange(e.target.value)} sx={{ width: 118, ...selectSx }}>
// //     {VIEW_MODES.map((v) => <MenuItem key={v.value} value={v.value} sx={{ fontSize: 13.5 }}>{v.label}</MenuItem>)}
// //   </Select>
// // );

// // /* "Start Date - End Date" with calendar button */
// // export const DateRangeField = ({ start, end, onChange }) => {
// //   const [anchorEl, setAnchorEl] = useState(null);
// //   const [s, setS] = useState("");
// //   const [e, setE] = useState("");
// //   const open = (ev) => { setS(toDateInput(start)); setE(toDateInput(end)); setAnchorEl(ev.currentTarget.closest("[data-daterange]")); };
// //   const text = start && end ? `${fmtShortDate(start)} – ${fmtShortDate(end)}` : "";

// //   return (
// //     <>
// //       <Box data-daterange sx={{ display: "flex", width: 262 }}>
// //         <TextField size="small" placeholder="Start Date – End Date" value={text} onClick={open} fullWidth
// //           InputProps={{ readOnly: true, sx: { cursor: "pointer", borderTopRightRadius: 0, borderBottomRightRadius: 0 } }}
// //           sx={{ ...fieldSx, "& input": { cursor: "pointer" } }} />
// //         <IconButton aria-label="Pick dates" onClick={open}
// //           sx={{ width: 38, height: 36, borderRadius: "0 6px 6px 0", bgcolor: THEME.primary, color: "#fff", "&:hover": { bgcolor: "#1a5fc7" } }}>
// //           <CalendarIcon fontSize="small" />
// //         </IconButton>
// //       </Box>
// //       <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={() => setAnchorEl(null)} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
// //         <Stack spacing={1.5} sx={{ p: 2, width: 260 }}>
// //           <TextField size="small" type="date" label="Start Date" value={s} onChange={(ev) => setS(ev.target.value)} InputLabelProps={{ shrink: true }} />
// //           <TextField size="small" type="date" label="End Date" value={e} onChange={(ev) => setE(ev.target.value)} InputLabelProps={{ shrink: true }} />
// //           <Stack direction="row" spacing={1} justifyContent="flex-end">
// //             <Button size="small" onClick={() => { onChange(null, null); setAnchorEl(null); }}>Clear</Button>
// //             <Button size="small" variant="contained" disabled={!s || !e}
// //               onClick={() => { onChange(fromDateInput(s), fromDateInput(e)); setAnchorEl(null); }}>Apply</Button>
// //           </Stack>
// //         </Stack>
// //       </Popover>
// //     </>
// //   );
// // };

// // /* multi / single select (Autocomplete) */
// // export const MultiSelect = ({ placeholder, options, value, onChange, width = 200, getLabel = (o) => o }) => (
// //   <Autocomplete multiple size="small" limitTags={1} disableCloseOnSelect options={options} value={value}
// //     getOptionLabel={getLabel} onChange={(_, v) => onChange(v)} sx={{ width, ...fieldSx }}
// //     ChipProps={{ size: "small", sx: { maxWidth: 96, fontSize: 12 } }}
// //     renderInput={(params) => <TextField {...params} placeholder={value.length ? "" : placeholder} />} />
// // );

// // export const SingleSelect = ({ placeholder, options, value, onChange, width = 200, getLabel = (o) => o }) => (
// //   <Autocomplete size="small" options={options} value={value} getOptionLabel={getLabel} onChange={(_, v) => onChange(v)}
// //     sx={{ width, ...fieldSx }} renderInput={(params) => <TextField {...params} placeholder={placeholder} />} />
// // );

// // /* zoom / fullscreen / info */
// // export const ChartTools = ({ zoomIn, zoomOut, isFullscreen, toggleFullscreen, onInfo }) => (
// //   <Stack direction="row" spacing={0.5} alignItems="center">
// //     <Tooltip title="Zoom in"><IconButton aria-label="Zoom in" onClick={zoomIn} sx={toolSx}><ZoomInIcon fontSize="small" /></IconButton></Tooltip>
// //     <Tooltip title="Zoom out"><IconButton aria-label="Zoom out" onClick={zoomOut} sx={toolSx}><ZoomOutIcon fontSize="small" /></IconButton></Tooltip>
// //     <Tooltip title={isFullscreen ? "Exit full screen" : "Full screen"}>
// //       <IconButton aria-label="Full screen" onClick={toggleFullscreen} sx={toolSx}>
// //         {isFullscreen ? <FullscreenExitIcon fontSize="small" /> : <FullscreenIcon fontSize="small" />}
// //       </IconButton>
// //     </Tooltip>
// //     {onInfo && (
// //       <Tooltip title="How to use">
// //         <IconButton aria-label="Info" onClick={onInfo} sx={{ width: 36, height: 36, borderRadius: "6px", bgcolor: THEME.info, color: "#fff", "&:hover": { bgcolor: "#1488c9" } }}>
// //           <InfoIcon fontSize="small" />
// //         </IconButton>
// //       </Tooltip>
// //     )}
// //   </Stack>
// // );

// // export const InfoPopover = ({ anchorEl, onClose }) => (
// //   <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}>
// //     <Box sx={{ p: 2, width: 330, fontSize: 13, color: THEME.text }}>
// //       <Typography fontWeight={700} fontSize={14} mb={1}>How to read this chart</Typography>
// //       <Box component="ul" sx={{ m: 0, pl: 2.25, "& li": { mb: 0.5 } }}>
// //         <li>Each row is a station; each bar is a production order (PO) worked on it, one colour per PO.</li>
// //         <li>Hover a bar for the PO, part number, quantity, date, hours and minutes used.</li>
// //         <li>Daily &amp; Weekly show the hours of the shift ({pad(SHIFT_START)}:00 - {pad(SHIFT_END)}:00); Monthly &amp; Yearly show full days.</li>
// //         <li>The red line is the current time. Shaded columns are Sundays / holidays.</li>
// //         <li>Use the &lt; &gt; arrows to move period, the date field for a custom range, and the zoom buttons to stretch the timeline.</li>
// //         <li>Pick a PO (or click it in the legend) to highlight it; the others fade.</li>
// //       </Box>
// //     </Box>
// //   </Popover>
// // );

// // export const RefreshButton = ({ onClick, loading }) => (
// //   <Button variant="contained" startIcon={<RefreshIcon />} onClick={onClick} disabled={loading}
// //     sx={{ ...btnSx, width: "8rem", bgcolor: THEME.primary, "&:hover": { bgcolor: "#1a5fc7", boxShadow: "none" } }}>
// //     Refresh
// //   </Button>
// // );

// // export const ClearFiltersButton = ({ onClick }) => (
// //   <Button variant="contained" onClick={onClick}
// //     sx={{ ...btnSx, width: "8rem", bgcolor: THEME.dark, "&:hover": { bgcolor: "#4a5361", boxShadow: "none" } }}>
// //     Clear Filters
// //   </Button>
// // );

// // /* legend: one colour per PO, click to highlight */
// // export const ProductionOrdersLegend = ({ pos, colorMap, focus, onPick, title = "Production Orders (click one to highlight it)" }) => (
// //   <Box sx={{ mt: 2.5, pt: 1.5, borderTop: `1px solid ${THEME.border}` }}>
// //     <Typography sx={{ fontSize: 13, fontWeight: 600, mb: 1, color: THEME.text }}>{title}</Typography>
// //     <Box sx={{ display: "flex", flexWrap: "wrap", gap: "6px 18px" }}>
// //       {pos.map((p) => (
// //         <Tooltip key={p.label} arrow title={`${p.part_number}${p.role ? " · " + p.role : ""} · qty ${p.quantity}`}>
// //           <Box onClick={() => onPick(focus === p.label ? "" : p.label)}
// //             sx={{
// //               display: "flex", alignItems: "center", gap: 0.75, fontSize: 12, color: focus === p.label ? THEME.text : THEME.muted,
// //               fontWeight: focus === p.label ? 700 : 400, cursor: "pointer", userSelect: "none", opacity: focus && focus !== p.label ? 0.5 : 1,
// //             }}>
// //             <Box sx={{ width: 13, height: 13, borderRadius: "3px", bgcolor: colorMap[p.label] }} />
// //             {p.label === p.production_order ? p.label : `${p.label} = ${p.production_order}`}
// //           </Box>
// //         </Tooltip>
// //       ))}
// //     </Box>
// //   </Box>
// // );

// // /* ------------------------------------------------------------------ *
// //  *  The Gantt itself - exported so it can be reused / tested with plain data
// //  * ------------------------------------------------------------------ */
// // export function PoGanttGrid({ data, view = "weekly", range, zoom = 1, availableWidth = 0, focus = "", expanded, onToggle, colorMap }) {
// //   const stations = data.stations || [];
// //   const rng = range || getRange(view, Date.now());
// //   const colors = colorMap || buildColorMap(data);
// //   const poInfo = useMemo(() => { const m = {}; (data.meta?.pos || []).forEach((p) => { m[p.label] = p; }); return m; }, [data.meta]);

// //   const { dayByDate, dayByWd, first, last } = useMemo(() => {
// //     const byDate = new Map(), byWd = new Map();
// //     (data.days || []).forEach((d) => { byDate.set(d.date, d); if (!d.is_holiday) byWd.set(d.working_day_no, d); });
// //     const dates = Array.from(byDate.keys()).sort();
// //     return { dayByDate: byDate, dayByWd: byWd, first: dates[0], last: dates[dates.length - 1] };
// //   }, [data.days]);

// //   // non-working: a holiday the server sent, a day skipped inside the schedule, or a Sunday outside it
// //   const isOff = (iso) => {
// //     const d = dayByDate.get(iso);
// //     if (d) return !!d.is_holiday;
// //     if (first && iso > first && iso < last) return true;
// //     return new Date(iso + "T00:00:00").getDay() === 0;
// //   };
// //   const wdText = (iso) => { const d = dayByDate.get(iso); return d ? (d.is_holiday ? "Off" : `WD ${d.working_day_no}`) : ""; };

// //   const scale = useMemo(
// //     () => buildScale({ view, range: rng, zoom, availableWidth, isOff, wdText }),
// //     // eslint-disable-next-line react-hooks/exhaustive-deps
// //     [view, rng.start, rng.end, zoom, availableWidth, dayByDate],
// //   );

// //   const rows = useMemo(() => {
// //     const out = [];
// //     stations.forEach((st) => {
// //       const isLine = st.process_mode === "LINE" && (st.members || []).length > 0;
// //       const open = !!(expanded && expanded.has(st.station_id));
// //       out.push({ key: String(st.station_id), row: st, member: false, canExpand: isLine, open });
// //       if (isLine && open) st.members.forEach((m, i) => out.push({ key: `${st.station_id}-m${m.flow_step_id ?? i}`, row: m, member: true }));
// //     });
// //     return out;
// //   }, [stations, expanded]);

// //   // one bar per PO per working day, inside the shift window, shares of the day split equally between its POs
// //   const barsOf = (row) => {
// //     const out = [];
// //     (row.cells || []).forEach((c) => {
// //       const day = dayByWd.get(c.working_day_no);
// //       if (!day || !c.pos || !c.pos.length) return;
// //       const base = fromDateInput(day.date);
// //       if (base + DAY <= rng.start || base >= rng.end) return;
// //       const f = c.capacity_minutes > 0 ? Math.min(1, c.minutes_used / c.capacity_minutes) : 1;
// //       const per = (f * (SHIFT_END - SHIFT_START)) / c.pos.length;
// //       c.pos.forEach((po, i) => {
// //         const s = base + (SHIFT_START + i * per) * 3600e3;
// //         const e = base + (SHIFT_START + (i + 1) * per) * 3600e3;
// //         const x = scale.toX(s);
// //         out.push({ po, x, w: Math.max(scale.toX(e) - x, 2), s, e, cell: c, date: day.date });
// //       });
// //     });
// //     return out;
// //   };

// //   const bodyH = rows.length * ROW_H;
// //   const headH = LAYOUT.headerRow1 + LAYOUT.headerRow2;
// //   const now = Date.now();
// //   const nowH = new Date(now).getHours() + new Date(now).getMinutes() / 60;
// //   const showNow = now >= rng.start && now < rng.end && (!scale.windowed || (nowH >= scale.wStart && nowH <= scale.wEnd));

// //   const headCell = (c, top, h, key, extra = {}) => (
// //     <Box key={key} sx={{
// //       position: "absolute", left: c.x, top, width: c.w, height: h, boxSizing: "border-box", borderLeft: `1px solid ${THEME.gridStrong}`,
// //       display: "flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap", overflow: "hidden", fontSize: 12,
// //       ...(c.off ? { bgcolor: "#e3e7ee", color: THEME.muted } : {}), ...extra,
// //     }}>
// //       {c.label}
// //       {c.sub && scale.dayW >= 22 ? <Box component="span" sx={{ ml: 0.4, fontSize: 9.5, color: THEME.muted }}>{c.sub}</Box> : null}
// //     </Box>
// //   );

// //   return (
// //     <Box sx={{ display: "flex", width: LAYOUT.labelWidth + scale.totalWidth, minWidth: "100%" }}>
// //       {/* station labels */}
// //       <Box sx={{ position: "sticky", left: 0, zIndex: 3, flex: "0 0 auto", width: LAYOUT.labelWidth, bgcolor: "#fff", borderRight: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
// //         <Box sx={{
// //           position: "sticky", top: 0, zIndex: 4, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box",
// //           display: "flex", alignItems: "flex-end", px: 1.5, pb: 0.75, fontWeight: 700, fontSize: 12.5, color: THEME.text,
// //         }}>
// //           Station
// //         </Box>
// //         {rows.map(({ key, row, member, canExpand, open }) => (
// //           <Box key={key} sx={{
// //             height: ROW_H, boxSizing: "border-box", borderBottom: `1px solid ${THEME.gridSoft}`, display: "flex", alignItems: "center",
// //             px: 1.5, pl: member ? 3.5 : 1.5, gap: 0.5, bgcolor: member ? "#f9fafc" : "#fff",
// //           }}>
// //             {canExpand && (
// //               <Box onClick={() => onToggle && onToggle(row.station_id)} sx={{ cursor: "pointer", userSelect: "none", fontSize: 11, width: 14, color: THEME.muted }}>
// //                 {open ? "▾" : "▸"}
// //               </Box>
// //             )}
// //             <Box sx={{ minWidth: 0, flex: 1 }}>
// //               <Box sx={{ fontWeight: member ? 500 : 700, fontSize: 12.5, lineHeight: 1.25, color: THEME.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
// //                 {member ? row.step_name : row.name}
// //                 {canExpand ? <span style={{ fontWeight: 400, color: THEME.muted }}> ({(row.members || []).length} steps)</span> : null}
// //               </Box>
// //               {!member && (row.role || row.part_number) && (
// //                 <Box sx={{ fontSize: 10.5, color: THEME.muted, lineHeight: 1.15, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
// //                   {[row.role === "CHILD" ? "Child" : row.role === "MAIN" ? "Main" : "", row.part_number].filter(Boolean).join(" · ")}
// //                 </Box>
// //               )}
// //             </Box>
// //             {!member && row.shifts ? <Box sx={{ fontSize: 11, color: THEME.muted, flex: "0 0 auto" }}>{row.shifts} shift</Box> : null}
// //           </Box>
// //         ))}
// //       </Box>

// //       {/* timeline */}
// //       <Box sx={{ position: "relative", flex: "0 0 auto", width: scale.totalWidth }}>
// //         <Box sx={{ position: "sticky", top: 0, zIndex: 3, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
// //           {scale.row1.map((c, i) => headCell(c, 0, LAYOUT.headerRow1, `a${i}`, { fontWeight: 700, borderBottom: `1px solid ${THEME.gridSoft}` }))}
// //           {scale.row2.map((c, i) => headCell(c, LAYOUT.headerRow1, LAYOUT.headerRow2, `b${i}`, { borderLeft: `1px solid ${THEME.gridSoft}`, justifyContent: scale.windowed ? "flex-start" : "center", pl: scale.windowed ? 0.5 : 0, fontSize: 11.5 }))}
// //         </Box>

// //         <Box sx={{ position: "relative", height: bodyH }}>
// //           <svg width={scale.totalWidth} height={bodyH} style={{ position: "absolute", left: 0, top: 0 }}>
// //             {scale.offDays.map((o, i) => <rect key={`o${i}`} x={o.x} y={0} width={o.w} height={bodyH} fill={THEME.offDay} />)}
// //             {scale.grid.map((g, i) => <line key={`g${i}`} x1={g.x + 0.5} x2={g.x + 0.5} y1={0} y2={bodyH} stroke={g.strong ? THEME.gridStrong : THEME.gridSoft} />)}
// //             {rows.map((_, i) => <line key={`r${i}`} x1={0} x2={scale.totalWidth} y1={(i + 1) * ROW_H - 0.5} y2={(i + 1) * ROW_H - 0.5} stroke={THEME.gridSoft} />)}
// //           </svg>

// //           {rows.map(({ key, row }, i) => barsOf(row).map((b, k) => {
// //             const dim = !!focus && b.po !== focus;
// //             const pct = b.cell.capacity_minutes > 0 ? Math.round((100 * b.cell.minutes_used) / b.cell.capacity_minutes) : null;
// //             const info = poInfo[b.po];
// //             return (
// //               <Tooltip key={`${key}-${k}`} arrow title={
// //                 <Box sx={{ fontSize: 12 }}>
// //                   <div><b>{row.name || row.step_name}</b></div>
// //                   <div>PO: {info && info.label !== info.production_order ? `${b.po} = ${info.production_order}` : b.po}</div>
// //                   {info && <div>{info.part_number} · qty {info.quantity}</div>}
// //                   <div>{fmtLong(b.date)} · {hm(b.s)} - {hm(b.e)}</div>
// //                   {b.cell.pos.length > 1 && <div>Shares the station with: {b.cell.pos.filter((p) => p !== b.po).join(", ")}</div>}
// //                   <div>Station used {Math.round(b.cell.minutes_used)} of {Math.round(b.cell.capacity_minutes)} min that day{pct !== null ? ` (${pct}%)` : ""}</div>
// //                 </Box>
// //               }>
// //                 <Box sx={{
// //                   position: "absolute", left: b.x, top: i * ROW_H + LAYOUT.barPad, width: b.w, height: LAYOUT.laneHeight, boxSizing: "border-box",
// //                   bgcolor: colors[b.po] || PO_PALETTE[0], color: "#fff", borderRadius: "3px", px: b.w > 20 ? 0.75 : 0, overflow: "hidden",
// //                   display: "flex", flexDirection: "column", justifyContent: "center", lineHeight: 1.15, fontSize: 11.5, whiteSpace: "nowrap",
// //                   opacity: dim ? 0.25 : 1, boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.35)", cursor: "default",
// //                 }}>
// //                   {b.w >= 30 && <Box sx={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis" }}>{b.po}</Box>}
// //                   {b.w >= 96 && <Box sx={{ fontSize: 10.5, opacity: 0.92, overflow: "hidden", textOverflow: "ellipsis" }}>{hm(b.s)} - {hm(b.e)}</Box>}
// //                 </Box>
// //               </Tooltip>
// //             );
// //           }))}

// //           {showNow && <Box sx={{ position: "absolute", left: scale.toX(now), top: 0, width: 2, height: bodyH, bgcolor: THEME.nowLine, zIndex: 2, pointerEvents: "none" }} />}
// //         </Box>
// //       </Box>
// //     </Box>
// //   );
// // }

// // /* ------------------------------------------------------------------ *
// //  *  Page
// //  * ------------------------------------------------------------------ */
// // export default function ScheduleDashboard({ apiBase = DEFAULT_API }) {
// //   const [data, setData] = useState(null);
// //   const [allPos, setAllPos] = useState([]);            // every yet-to-start PO the backend knows (from the unfiltered load)
// //   const [poSel, setPoSel] = useState([]);              // POs to load - click order = load priority
// //   const [startDate, setStartDate] = useState("");      // empty = next working day
// //   const [timeSource, setTimeSource] = useState("actual");
// //   const [labelMode, setLabelMode] = useState("seq");
// //   const [showHolidays, setShowHolidays] = useState(false);
// //   const [focus, setFocus] = useState("");
// //   const [expanded, setExpanded] = useState(() => new Set());
// //   const [showWarn, setShowWarn] = useState(false);
// //   const [showAssume, setShowAssume] = useState(false);
// //   const [loading, setLoading] = useState(false);
// //   const [exporting, setExporting] = useState(false);
// //   const [error, setError] = useState("");
// //   const [isFullscreen, setIsFullscreen] = useState(false);
// //   const fsRef = useRef(null);

// //   /* view / filter state */
// //   const [view, setView] = useState("weekly");
// //   const [anchor, setAnchor] = useState(() => Date.now());
// //   const [customStart, setCustomStart] = useState(null);
// //   const [customEnd, setCustomEnd] = useState(null);
// //   const [zoom, setZoom] = useState(1);
// //   const [stationSel, setStationSel] = useState([]);
// //   const [infoAnchor, setInfoAnchor] = useState(null);
// //   const [gridEl, setGridEl] = useState(null);
// //   const [gridW, setGridW] = useState(0);

// //   const authHeaders = () => ({ "x-access-token": localStorage.getItem("token") || "" });   // read at request time
// //   const query = () => buildQuery({ pos: poSel, startDate, timeSource, labelMode, showHolidays });

// //   useEffect(() => {
// //     const onChange = () => setIsFullscreen(!!document.fullscreenElement);
// //     document.addEventListener("fullscreenchange", onChange);
// //     return () => document.removeEventListener("fullscreenchange", onChange);
// //   }, []);
// //   const toggleFullscreen = () => {
// //     if (document.fullscreenElement) document.exitFullscreen();
// //     else if (fsRef.current) fsRef.current.requestFullscreen();
// //   };

// //   // width of the chart area, so short periods stretch to fill the screen
// //   useEffect(() => {
// //     if (!gridEl) return undefined;
// //     setGridW(gridEl.clientWidth);
// //     if (typeof ResizeObserver === "undefined") return undefined;
// //     const ro = new ResizeObserver((entries) => setGridW(entries[0].contentRect.width));
// //     ro.observe(gridEl);
// //     return () => ro.disconnect();
// //   }, [gridEl]);

// //   const generate = async () => {
// //     setLoading(true);
// //     setError("");
// //     try {
// //       const res = await axios.get(`${apiBase}/schedule/po-gantt?${query()}`, { headers: authHeaders() });
// //       const d = res.data;
// //       if (!d?.stations?.length) {
// //         setData(null);
// //         setError("No yet-to-start production orders could be scheduled.");
// //         return;
// //       }
// //       const first = d.meta?.start_date || d.days?.[0]?.date;
// //       if (first && first !== (data?.meta?.start_date || data?.days?.[0]?.date)) {   // new schedule start -> show it
// //         setAnchor(fromDateInput(first));
// //         setCustomStart(null);
// //         setCustomEnd(null);
// //       }
// //       setData(d);
// //       setFocus("");
// //       setStationSel([]);
// //       if (!poSel.length) setAllPos(d.meta?.pos || []);       // keep the full list for the PO picker
// //     } catch (err) {
// //       console.error(err);
// //       setData(null);
// //       setError(await errorText(err, "Failed to generate the schedule."));
// //     } finally {
// //       setLoading(false);
// //     }
// //   };

// //   const exportXlsx = async () => {
// //     setExporting(true);
// //     try {
// //       const res = await axios.get(`${apiBase}/schedule/po-gantt/export?${query()}`, { headers: authHeaders(), responseType: "blob" });
// //       const url = URL.createObjectURL(res.data);
// //       const a = document.createElement("a");
// //       a.href = url;
// //       a.download = "po_gantt.xlsx";
// //       document.body.appendChild(a);
// //       a.click();
// //       a.remove();
// //       URL.revokeObjectURL(url);
// //     } catch (err) {
// //       setError(await errorText(err, "Export failed."));
// //     } finally {
// //       setExporting(false);
// //     }
// //   };

// //   const toggleExpand = (id) =>
// //     setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

// //   /* ---- view controls ---- */
// //   const scheduleStart = () => {
// //     const first = data?.meta?.start_date || data?.days?.[0]?.date;
// //     return first ? fromDateInput(first) : Date.now();
// //   };
// //   const changeView = (v) => { setView(v); setCustomStart(null); setCustomEnd(null); setZoom(1); };
// //   const range = useMemo(() => getRange(view, anchor, customStart, customEnd), [view, anchor, customStart, customEnd]);
// //   const navigate = (dir) => setAnchor((a) => shiftAnchor(view, a, dir, range));
// //   const zoomIn = () => setZoom((z) => Math.min(ZOOM.max, z + ZOOM.step));
// //   const zoomOut = () => setZoom((z) => Math.max(ZOOM.min, z - ZOOM.step));
// //   const clearFilters = () => {
// //     setStationSel([]);
// //     setFocus("");
// //     setCustomStart(null);
// //     setCustomEnd(null);
// //     setZoom(1);
// //     setAnchor(scheduleStart());
// //   };

// //   const meta = data?.meta;
// //   const warnings = data?.warnings || [];
// //   const assumptions = data?.assumptions || [];
// //   const poOptions = allPos.length ? allPos : meta?.pos || [];
// //   const colorMap = useMemo(() => buildColorMap(data), [data]);

// //   const stationOptions = useMemo(() => Array.from(new Set((data?.stations || []).map((s) => s.name))), [data]);
// //   const gridData = useMemo(() => {
// //     if (!data) return null;
// //     if (!stationSel.length) return data;
// //     return { ...data, stations: (data.stations || []).filter((s) => stationSel.includes(s.name)) };
// //   }, [data, stationSel]);

// //   const poLabelText = (label) => {
// //     const p = (meta?.pos || []).find((x) => x.label === label);
// //     return p && p.label !== p.production_order ? `${p.label} = ${p.production_order}` : label;
// //   };

// //   const rangeEndInclusive = addDays(range.end, -1);
// //   const hasWorkInRange = useMemo(() => {
// //     const a = toDateInput(range.start), b = toDateInput(rangeEndInclusive);
// //     return (data?.days || []).some((d) => !d.is_holiday && d.date >= a && d.date <= b);
// //   }, [data, range, rangeEndInclusive]);
// //   const periodText = `${fmtShortDate(range.start)}${range.end - range.start > DAY ? ` – ${fmtShortDate(rangeEndInclusive)}` : ""}`;

// //   return (
// //     <Box ref={fsRef} sx={{ p: 2.5, bgcolor: isFullscreen ? "#fff" : "transparent", overflow: "auto", height: isFullscreen ? "100vh" : "auto" }}>
// //       <Box sx={{ bgcolor: "#fff", border: `1px solid ${THEME.border}`, borderRadius: "10px", p: 2.5 }}>
// //         <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
// //           <Typography variant="h6" sx={{ color: "#333", fontWeight: 600 }}>Production Order Schedule - PO on Station</Typography>
// //           <Stack direction="row" sx={{ gap: 1 }}>
// //             <Button variant="outlined" onClick={exportXlsx} disabled={!data || exporting} sx={{ ...btnSx, borderColor: THEME.primary }}>{exporting ? "Exporting..." : "Export Excel"}</Button>
// //             <Button variant="contained" onClick={generate} disabled={loading} sx={{ ...btnSx, bgcolor: THEME.primary, "&:hover": { bgcolor: "#1a5fc7", boxShadow: "none" } }}>{loading ? "Scheduling..." : "Generate Schedule"}</Button>
// //           </Stack>
// //         </Stack>

// //         {/* inputs */}
// //         <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 1 }}>
// //           <Select
// //             size="small" multiple displayEmpty value={poSel}
// //             onChange={(e) => setPoSel(typeof e.target.value === "string" ? e.target.value.split(",") : e.target.value)}
// //             renderValue={(sel) => (sel.length ? `${sel.length} PO(s): ${sel.join(", ")}` : "All yet-to-start POs")}
// //             sx={{ width: 280, ...selectSx }}
// //           >
// //             {poOptions.length === 0 && <MenuItem disabled value="">Generate once to list the POs</MenuItem>}
// //             {poOptions.map((p) => (
// //               <MenuItem key={p.production_order} value={p.production_order}>
// //                 {p.production_order} - {p.part_number} ({p.quantity})
// //               </MenuItem>
// //             ))}
// //           </Select>
// //           <TextField
// //             size="small" type="date" label="Start date" InputLabelProps={{ shrink: true }} sx={{ width: 170, ...fieldSx }}
// //             value={startDate} onChange={(e) => setStartDate(e.target.value)}
// //           />
// //           <Select size="small" value={timeSource} onChange={(e) => setTimeSource(e.target.value)} sx={{ minWidth: 150, ...selectSx }}>
// //             <MenuItem value="actual">Actual time</MenuItem>
// //             <MenuItem value="sap">SAP time</MenuItem>
// //           </Select>
// //           <Select size="small" value={labelMode} onChange={(e) => setLabelMode(e.target.value)} sx={{ minWidth: 170, ...selectSx }}>
// //             <MenuItem value="seq">Labels: B1, B2...</MenuItem>
// //             <MenuItem value="po">Labels: PO number</MenuItem>
// //           </Select>
// //           <FormControlLabel
// //             control={<Switch size="small" checked={showHolidays} onChange={(e) => setShowHolidays(e.target.checked)} />}
// //             label={<span style={{ fontSize: 13 }}>Show off days</span>}
// //           />
// //           {poSel.length > 0 && <Button size="small" onClick={() => setPoSel([])}>Load all</Button>}
// //         </Stack>
// //         <Typography sx={{ fontSize: 12, color: THEME.muted, mb: 1.5, textAlign: "center" }}>
// //           POs are loaded in the order you pick them (first picked = first on the line). Press "Generate Schedule" after changing any input.
// //         </Typography>

// //         {/* view / filter toolbar */}
// //         <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 2 }}>
// //           <ViewSelect value={view} onChange={changeView} />
// //           <Stack direction="row" alignItems="center">
// //             <Tooltip title="Previous"><span><IconButton aria-label="Previous" size="small" disabled={!!range.custom} onClick={() => navigate(-1)} sx={toolSx}><PrevIcon fontSize="small" /></IconButton></span></Tooltip>
// //             <Tooltip title="Next"><span><IconButton aria-label="Next" size="small" disabled={!!range.custom} onClick={() => navigate(1)} sx={toolSx}><NextIcon fontSize="small" /></IconButton></span></Tooltip>
// //           </Stack>
// //           <DateRangeField
// //             start={customStart || range.start} end={customEnd || rangeEndInclusive}
// //             onChange={(s, e) => { setCustomStart(s); setCustomEnd(e); }}
// //           />
// //           <MultiSelect placeholder="All stations" options={stationOptions} value={stationSel} onChange={setStationSel} width={230} />
// //           <SingleSelect
// //             placeholder="Highlight PO" options={(meta?.pos || []).map((p) => p.label)} value={focus || null}
// //             onChange={(v) => setFocus(v || "")} getLabel={poLabelText} width={200}
// //           />
// //           <ChartTools
// //             zoomIn={zoomIn} zoomOut={zoomOut} isFullscreen={isFullscreen} toggleFullscreen={toggleFullscreen}
// //             onInfo={(e) => setInfoAnchor(e.currentTarget)}
// //           />
// //           <ClearFiltersButton onClick={clearFilters} />
// //           {/* <RefreshButton onClick={generate} loading={loading} /> */}
// //         </Stack>
// //         <InfoPopover anchorEl={infoAnchor} onClose={() => setInfoAnchor(null)} />

// //         {loading && <LinearProgress sx={{ mb: 1 }} />}
// //         {error && <Alert severity="warning" sx={{ mb: 2 }}><b>Notice:</b> {error}</Alert>}

// //         {data ? (
// //           <>
// //             <Box sx={{ bgcolor: "#f6f8fb", borderRadius: "8px", px: 2, py: 1.25, mb: 2, fontSize: 13, color: "#374151" }}>
// //               <b>{meta?.number_of_pos ?? meta?.pos?.length ?? 0}</b> PO(s) loaded - {fmtLong(meta?.start_date)} to <b>{fmtLong(meta?.finish_date)}</b> over{" "}
// //               <b>{meta?.working_days ?? (data.days || []).filter((d) => !d.is_holiday).length}</b> working day(s).
// //               <Box component="span" sx={{ ml: 1.5, color: THEME.muted }}>Showing {periodText}</Box>
// //             </Box>

// //             {warnings.length > 0 && (
// //               <Alert severity="warning" sx={{ mb: 2 }}
// //                 action={<Button color="inherit" size="small" onClick={() => setShowWarn(!showWarn)}>{showWarn ? "Hide" : "Show"}</Button>}>
// //                 {warnings.length} warning(s)
// //                 <Collapse in={showWarn}>
// //                   <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5, maxHeight: 200, overflow: "auto" }}>
// //                     {warnings.map((w, i) => <li key={i}>{w}</li>)}
// //                   </Box>
// //                 </Collapse>
// //               </Alert>
// //             )}

// //             {!hasWorkInRange && (
// //               <Alert severity="info" sx={{ mb: 2 }}
// //                 action={<Button color="inherit" size="small" onClick={clearFilters}>Go to schedule start</Button>}>
// //                 No scheduled work in this period.
// //               </Alert>
// //             )}

// //             {/* gantt */}
// //             <Box ref={setGridEl} sx={{ border: `1px solid ${THEME.border}`, borderRadius: "8px", bgcolor: "#fff", overflow: "auto", maxHeight: isFullscreen ? "calc(100vh - 360px)" : "70vh" }}>
// //               <PoGanttGrid
// //                 data={gridData} view={view} range={range} zoom={zoom} availableWidth={gridW - LAYOUT.labelWidth - 2}
// //                 focus={focus} expanded={expanded} onToggle={toggleExpand} colorMap={colorMap}
// //               />
// //             </Box>

// //             <ProductionOrdersLegend pos={meta?.pos || []} colorMap={colorMap} focus={focus} onPick={setFocus} />

// //             {assumptions.length > 0 && (
// //               <Box sx={{ mt: 1.5 }}>
// //                 <Button size="small" onClick={() => setShowAssume(!showAssume)}>{showAssume ? "Hide" : "Show"} assumptions ({assumptions.length})</Button>
// //                 <Collapse in={showAssume}>
// //                   <Box component="ul" sx={{ m: 0, pl: 2.5, fontSize: 12, color: "#4b5563" }}>
// //                     {assumptions.map((a, i) => <li key={i}>{a}</li>)}
// //                   </Box>
// //                 </Collapse>
// //               </Box>
// //             )}

// //             <Typography sx={{ fontSize: 12, color: THEME.muted, mt: 1 }}>
// //               Each row is a station and each bar a PO, drawn within the {pad(SHIFT_START)}:00 - {pad(SHIFT_END)}:00 shift (Sundays, 1st / 3rd Saturdays and holidays are skipped).
// //               Hover a bar for the hours and minutes used. Use the arrow on "SMT Line" to see its individual steps.
// //             </Typography>
// //           </>
// //         ) : (
// //           !loading && !error && (
// //             <Box sx={{ textAlign: "center", p: 6, color: "#666", bgcolor: "#f8f9fa", borderRadius: "8px" }}>
// //               Click "Generate Schedule" to load the yet-to-start production orders onto the stations.
// //             </Box>
// //           )
// //         )}
// //       </Box>
// //     </Box>
// //   );
// // }




// import React, { useEffect, useMemo, useRef, useState } from "react";
// import axios from "axios";
// import {
//   Alert, Autocomplete, Box, Button, Collapse, FormControlLabel, IconButton, LinearProgress, MenuItem,
//   Popover, Select, Stack, Switch, TextField, Tooltip, Typography,
// } from "@mui/material";
// import {
//   CalendarMonth as CalendarIcon, ZoomIn as ZoomInIcon, ZoomOut as ZoomOutIcon, OpenInFull as FullscreenIcon,
//   FullscreenExit as FullscreenExitIcon, InfoOutlined as InfoIcon, Refresh as RefreshIcon,
//   ChevronLeft as PrevIcon, ChevronRight as NextIcon,
// } from "@mui/icons-material";

// /* ------------------------------------------------------------------ *
//  *  "PO on Station" Gantt   (rows = stations, bars = POs, one colour per PO)
//  *
//  *  Backend:  GET {apiBase}/schedule/po-gantt          (see po_gantt_service.py)
//  *            GET {apiBase}/schedule/po-gantt/export   (same params, .xlsx)
//  *  Only needs react, axios, @mui/material and @mui/icons-material.
//  *
//  *  Bars are drawn at the REAL start / end time of each PO on a station (stations[].po_runs), so a PO is only ever on
//  *  one stage at a time. A run that goes over a Sunday / holiday is cut there and the off day stays blank.
//  *  A station group (e.g. the SMT line) arrives as ONE row (process_mode "LINE", step_names[]); its stages are not rows.
//  * ------------------------------------------------------------------ */

// const DEFAULT_API = "http://localhost:2002";

// /* ---------- constants (from the schedule config) ---------- */
// const PO_PALETTE = [
//   "#1e88e5", "#f59e0b", "#10b981", "#e11d48", "#8b5cf6", "#14b8a6",
//   "#f97316", "#84cc16", "#ec4899", "#0ea5e9", "#a16207", "#6366f1",
// ];
// const VIEW_MODES = [
//   { value: "daily", label: "Daily" },
//   { value: "weekly", label: "Weekly" },
//   { value: "monthly", label: "Monthly" },
//   { value: "yearly", label: "Yearly" },
// ];
// const THEME = {
//   primary: "#1f6fe5", info: "#1b9ae1", dark: "#5b6573", border: "#e3e7ee", gridStrong: "#c9d0da", gridSoft: "#eceff4",
//   text: "#1f2937", muted: "#6b7280", nowLine: "#ef4444", offDay: "rgba(100,116,139,0.10)", headBg: "#f4f6fa",
// };
// const LAYOUT = { labelWidth: 270, headerRow1: 30, headerRow2: 28, barPad: 4, laneHeight: 34 };
// const ROW_H = LAYOUT.laneHeight + 2 * LAYOUT.barPad;
// const BASE_DAY_WIDTH = { daily: 900, weekly: 156, monthly: 46, yearly: 3.2 };   // px per day at zoom = 1
// const ZOOM = { min: 0.5, max: 6, step: 0.5 };
// const MAX_CUSTOM_RANGE_DAYS = 400;
// const SHIFT_START = 6;   // first hour drawn in daily / weekly view
// const SHIFT_END = 20;    // last hour drawn (06:00 - 20:00)

// /* ---------- date helpers ---------- */
// const DAY = 24 * 3600 * 1000;
// const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
// const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
// const pad = (n) => String(n).padStart(2, "0");
// const toDateInput = (ts) => {
//   if (!ts) return "";
//   const d = new Date(ts);
//   return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
// };
// const fromDateInput = (s) => {
//   if (!s) return null;
//   const [y, m, d] = s.split("-").map(Number);
//   return new Date(y, m - 1, d).getTime();
// };
// const startOfDay = (ts) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };
// const addDays = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n).getTime(); };
// const addMonths = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth() + n, 1).getTime(); };
// const startOfWeekMon = (ts) => { const d = new Date(startOfDay(ts)); return addDays(d.getTime(), -((d.getDay() + 6) % 7)); };
// const fmtShortDate = (ts) => { const d = new Date(ts); return `${pad(d.getDate())} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; };
// const fmtLong = (iso) =>
//   iso ? new Date(iso + "T00:00:00").toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" }) : "-";
// const dayLabel = (ts) => { const d = new Date(ts); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
// const hm = (ts) => { const d = new Date(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

// // anchor = any timestamp inside the period being shown
// function getRange(view, anchor, customStart, customEnd) {
//   if (customStart && customEnd) {
//     const s = startOfDay(Math.min(customStart, customEnd));
//     let e = addDays(startOfDay(Math.max(customStart, customEnd)), 1);
//     if ((e - s) / DAY > MAX_CUSTOM_RANGE_DAYS) e = addDays(s, MAX_CUSTOM_RANGE_DAYS);
//     return { start: s, end: e, custom: true };
//   }
//   switch (view) {
//     case "daily": { const s = startOfDay(anchor); return { start: s, end: addDays(s, 1) }; }
//     case "weekly": { const s = startOfWeekMon(anchor); return { start: s, end: addDays(s, 7) }; }
//     case "monthly": { const s = addMonths(anchor, 0); return { start: s, end: addMonths(s, 1) }; }
//     default: { const s = addMonths(anchor, -1); return { start: s, end: addMonths(s, 12) }; }   // yearly
//   }
// }
// function shiftAnchor(view, anchor, dir, range) {
//   if (range?.custom) return anchor;
//   switch (view) {
//     case "daily": return addDays(anchor, dir);
//     case "weekly": return addDays(anchor, 7 * dir);
//     case "monthly": return addMonths(anchor, dir);
//     default: return addMonths(anchor, 12 * dir);
//   }
// }

// /* ---------- the time axis ----------
//  * Daily / Weekly draw only the working window of each day (06:00-20:00) with a label for the hours;
//  * Monthly / Yearly draw the full 24 h.  toX converts a timestamp to a pixel x inside the timeline. */
// function buildScale({ view, range, zoom, availableWidth, isOff, wdText }) {
//   const windowed = view === "daily" || view === "weekly";
//   const wStart = windowed ? SHIFT_START : 0;
//   const wEnd = windowed ? SHIFT_END : 24;
//   const hours = wEnd - wStart;

//   const days = [];
//   for (let t = range.start; t < range.end; t = addDays(t, 1)) days.push(t);

//   let baseDay = BASE_DAY_WIDTH[view] || 100;
//   if (view === "daily" && days.length > 1) baseDay = BASE_DAY_WIDTH.weekly;
//   const fill = Math.max(0, availableWidth) / Math.max(days.length, 1);
//   const dayW = Math.max(baseDay, fill) * zoom;
//   const totalWidth = dayW * days.length;
//   const winStart = (i) => days[i] + wStart * 3600e3;
//   const winLen = hours * 3600e3;

//   const dayIndexOf = (ts) => {
//     if (ts <= days[0]) return -1;
//     let lo = 0, hi = days.length - 1;
//     while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (days[mid] <= ts) lo = mid; else hi = mid - 1; }
//     return ts >= range.end ? days.length : lo;
//   };
//   const toX = (ts) => {
//     const i = dayIndexOf(ts);
//     if (i < 0) return 0;
//     if (i >= days.length) return totalWidth;
//     const frac = Math.min(1, Math.max(0, (ts - winStart(i)) / winLen));
//     return i * dayW + frac * dayW;
//   };

//   const row1 = [], row2 = [], grid = [];
//   const groupBy = (keyFn, labelFn, target) => {
//     let startIdx = 0;
//     for (let i = 1; i <= days.length; i++) {
//       if (i === days.length || keyFn(days[i]) !== keyFn(days[startIdx])) {
//         target.push({ x: startIdx * dayW, w: (i - startIdx) * dayW, label: labelFn(days[startIdx], i - startIdx) });
//         startIdx = i;
//       }
//     }
//   };
//   const hourPx = dayW / hours;

//   if (windowed) {
//     days.forEach((d, i) => {
//       const dt = new Date(d);
//       const wd = wdText(toDateInput(d));
//       row1.push({
//         x: i * dayW, w: dayW, off: isOff(toDateInput(d)),
//         label: dayW >= 170 ? `${dayLabel(d)}${wd ? " · " + wd : ""}` : dayW >= 90 ? dayLabel(d) : String(dt.getDate()),
//       });
//       const step = [1, 2, 3, 4, 6, 12].find((s) => s * hourPx >= 46) || hours;      // hour labels never overlap
//       for (let h = wStart; h < wEnd; h += step) {
//         const next = Math.min(h + step, wEnd);
//         row2.push({ x: i * dayW + ((h - wStart) / hours) * dayW, w: ((next - h) / hours) * dayW, label: `${pad(h)}:00` });
//       }
//       if (hourPx >= 6 && days.length <= 31) for (let h = wStart + 1; h < wEnd; h++) grid.push({ x: i * dayW + ((h - wStart) / hours) * dayW, strong: false });
//     });
//   } else if (view === "monthly") {
//     groupBy((t) => `${new Date(t).getFullYear()}-${new Date(t).getMonth()}`, (t) => `${MONTHS_LONG[new Date(t).getMonth()]} ${new Date(t).getFullYear()}`, row1);
//     days.forEach((d, i) => row2.push({ x: i * dayW, w: dayW, label: String(new Date(d).getDate()), sub: WEEKDAYS[new Date(d).getDay()][0], off: isOff(toDateInput(d)) }));
//   } else {
//     groupBy((t) => new Date(t).getFullYear(), (t) => String(new Date(t).getFullYear()), row1);
//     groupBy((t) => `${new Date(t).getFullYear()}-${new Date(t).getMonth()}`, (t, n) => (n * dayW < 30 ? MONTHS[new Date(t).getMonth()][0] : MONTHS[new Date(t).getMonth()]), row2);
//   }
//   if (!windowed) row2.forEach((c) => grid.push({ x: c.x, strong: false }));
//   row1.forEach((c) => grid.push({ x: c.x, strong: true }));

//   const offDays = [];
//   if (dayW >= 12) days.forEach((d, i) => { if (isOff(toDateInput(d))) offDays.push({ x: i * dayW, w: dayW }); });

//   return { days, dayW, totalWidth, toX, row1, row2, grid, offDays, windowed, wStart, wEnd };
// }

// /* ---------- misc ---------- */
// const buildQuery = ({ pos, startDate, timeSource, labelMode, showHolidays }) => {
//   const q = new URLSearchParams();
//   pos.forEach((p) => q.append("production_order", p));          // repeated param, order = load priority
//   if (startDate) q.append("start_date", startDate);
//   q.append("time_source", timeSource);
//   q.append("label_mode", labelMode);
//   q.append("show_holidays", String(showHolidays));
//   return q.toString();
// };

// const errorText = async (err, fallback) => {
//   try {
//     let data = err.response?.data;
//     if (data instanceof Blob) data = JSON.parse(await data.text());   // export errors arrive as a blob
//     const d = data?.detail;
//     if (typeof d === "string") return d;
//     if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
//   } catch (_) { /* ignore */ }
//   return err.message ? `${fallback} (${err.message})` : fallback;
// };

// // one colour per PO label (first colour = blue, used when a single PO is shown)
// export function buildColorMap(data) {
//   const labels = (data?.meta?.pos || []).map((p) => p.label);
//   const seen = new Set(labels);
//   const rows = (data?.stations || []).flatMap((s) => [s, ...(s.members || [])]);
//   rows.forEach((r) => (r.cells || []).forEach((c) => (c.pos || []).forEach((p) => { if (!seen.has(p)) { seen.add(p); labels.push(p); } })));
//   const map = {};
//   labels.forEach((l, i) => { map[l] = PO_PALETTE[i % PO_PALETTE.length]; });
//   return map;
// }

// /* ------------------------------------------------------------------ *
//  *  Toolbar components
//  * ------------------------------------------------------------------ */
// const fieldSx = {
//   "& .MuiOutlinedInput-root": { borderRadius: "6px", fontSize: 13.5, bgcolor: "#fff", minHeight: 36 },
//   "& .MuiOutlinedInput-notchedOutline": { borderColor: THEME.border },
// };
// const selectSx = { height: 36, fontSize: 13.5, borderRadius: "6px", bgcolor: "#fff", "& .MuiOutlinedInput-notchedOutline": { borderColor: THEME.border } };
// const toolSx = { width: 34, height: 34, color: THEME.primary, "&:hover": { bgcolor: "#eef3fb" } };
// const btnSx = { height: 36, textTransform: "none", fontWeight: 600, fontSize: 13.5, boxShadow: "none", whiteSpace: "nowrap" };

// /* Weekly / Daily / Monthly / Yearly */
// export const ViewSelect = ({ value, onChange }) => (
//   <Select size="small" value={value} onChange={(e) => onChange(e.target.value)} sx={{ width: 118, ...selectSx }}>
//     {VIEW_MODES.map((v) => <MenuItem key={v.value} value={v.value} sx={{ fontSize: 13.5 }}>{v.label}</MenuItem>)}
//   </Select>
// );

// /* "Start Date - End Date" with calendar button */
// export const DateRangeField = ({ start, end, onChange }) => {
//   const [anchorEl, setAnchorEl] = useState(null);
//   const [s, setS] = useState("");
//   const [e, setE] = useState("");
//   const open = (ev) => { setS(toDateInput(start)); setE(toDateInput(end)); setAnchorEl(ev.currentTarget.closest("[data-daterange]")); };
//   const text = start && end ? `${fmtShortDate(start)} – ${fmtShortDate(end)}` : "";

//   return (
//     <>
//       <Box data-daterange sx={{ display: "flex", width: 262 }}>
//         <TextField size="small" placeholder="Start Date – End Date" value={text} onClick={open} fullWidth
//           InputProps={{ readOnly: true, sx: { cursor: "pointer", borderTopRightRadius: 0, borderBottomRightRadius: 0 } }}
//           sx={{ ...fieldSx, "& input": { cursor: "pointer" } }} />
//         <IconButton aria-label="Pick dates" onClick={open}
//           sx={{ width: 38, height: 36, borderRadius: "0 6px 6px 0", bgcolor: THEME.primary, color: "#fff", "&:hover": { bgcolor: "#1a5fc7" } }}>
//           <CalendarIcon fontSize="small" />
//         </IconButton>
//       </Box>
//       <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={() => setAnchorEl(null)} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
//         <Stack spacing={1.5} sx={{ p: 2, width: 260 }}>
//           <TextField size="small" type="date" label="Start Date" value={s} onChange={(ev) => setS(ev.target.value)} InputLabelProps={{ shrink: true }} />
//           <TextField size="small" type="date" label="End Date" value={e} onChange={(ev) => setE(ev.target.value)} InputLabelProps={{ shrink: true }} />
//           <Stack direction="row" spacing={1} justifyContent="flex-end">
//             <Button size="small" onClick={() => { onChange(null, null); setAnchorEl(null); }}>Clear</Button>
//             <Button size="small" variant="contained" disabled={!s || !e}
//               onClick={() => { onChange(fromDateInput(s), fromDateInput(e)); setAnchorEl(null); }}>Apply</Button>
//           </Stack>
//         </Stack>
//       </Popover>
//     </>
//   );
// };

// /* multi / single select (Autocomplete) */
// export const MultiSelect = ({ placeholder, options, value, onChange, width = 200, getLabel = (o) => o }) => (
//   <Autocomplete multiple size="small" limitTags={1} disableCloseOnSelect options={options} value={value}
//     getOptionLabel={getLabel} onChange={(_, v) => onChange(v)} sx={{ width, ...fieldSx }}
//     ChipProps={{ size: "small", sx: { maxWidth: 96, fontSize: 12 } }}
//     renderInput={(params) => <TextField {...params} placeholder={value.length ? "" : placeholder} />} />
// );

// export const SingleSelect = ({ placeholder, options, value, onChange, width = 200, getLabel = (o) => o }) => (
//   <Autocomplete size="small" options={options} value={value} getOptionLabel={getLabel} onChange={(_, v) => onChange(v)}
//     sx={{ width, ...fieldSx }} renderInput={(params) => <TextField {...params} placeholder={placeholder} />} />
// );

// /* zoom / fullscreen / info */
// export const ChartTools = ({ zoomIn, zoomOut, isFullscreen, toggleFullscreen, onInfo }) => (
//   <Stack direction="row" spacing={0.5} alignItems="center">
//     <Tooltip title="Zoom in"><IconButton aria-label="Zoom in" onClick={zoomIn} sx={toolSx}><ZoomInIcon fontSize="small" /></IconButton></Tooltip>
//     <Tooltip title="Zoom out"><IconButton aria-label="Zoom out" onClick={zoomOut} sx={toolSx}><ZoomOutIcon fontSize="small" /></IconButton></Tooltip>
//     <Tooltip title={isFullscreen ? "Exit full screen" : "Full screen"}>
//       <IconButton aria-label="Full screen" onClick={toggleFullscreen} sx={toolSx}>
//         {isFullscreen ? <FullscreenExitIcon fontSize="small" /> : <FullscreenIcon fontSize="small" />}
//       </IconButton>
//     </Tooltip>
//     {onInfo && (
//       <Tooltip title="How to use">
//         <IconButton aria-label="Info" onClick={onInfo} sx={{ width: 36, height: 36, borderRadius: "6px", bgcolor: THEME.info, color: "#fff", "&:hover": { bgcolor: "#1488c9" } }}>
//           <InfoIcon fontSize="small" />
//         </IconButton>
//       </Tooltip>
//     )}
//   </Stack>
// );

// export const InfoPopover = ({ anchorEl, onClose }) => (
//   <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}>
//     <Box sx={{ p: 2, width: 330, fontSize: 13, color: THEME.text }}>
//       <Typography fontWeight={700} fontSize={14} mb={1}>How to read this chart</Typography>
//       <Box component="ul" sx={{ m: 0, pl: 2.25, "& li": { mb: 0.5 } }}>
//         <li>Each row is a station (stages are listed child first, then main); each bar is a production order (PO) worked on it, one colour per PO. A PO is on one stage at a time.</li>
//         <li>Hover a bar for the PO, part number, quantity and the exact start and end time. A row such as the SMT line combines several stages - hover its name to list them.</li>
//         <li>Daily &amp; Weekly show the hours of the shift ({pad(SHIFT_START)}:00 - {pad(SHIFT_END)}:00); Monthly &amp; Yearly show full days.</li>
//         <li>The red line is the current time. Shaded columns are Sundays / holidays.</li>
//         <li>Use the &lt; &gt; arrows to move period, the date field for a custom range, and the zoom buttons to stretch the timeline.</li>
//         <li>Pick a PO (or click it in the legend) to highlight it; the others fade.</li>
//       </Box>
//     </Box>
//   </Popover>
// );

// export const RefreshButton = ({ onClick, loading }) => (
//   <Button variant="contained" startIcon={<RefreshIcon />} onClick={onClick} disabled={loading}
//     sx={{ ...btnSx, width: "8rem", bgcolor: THEME.primary, "&:hover": { bgcolor: "#1a5fc7", boxShadow: "none" } }}>
//     Refresh
//   </Button>
// );

// export const ClearFiltersButton = ({ onClick }) => (
//   <Button variant="contained" onClick={onClick}
//     sx={{ ...btnSx, width: "8rem", bgcolor: THEME.dark, "&:hover": { bgcolor: "#4a5361", boxShadow: "none" } }}>
//     Clear Filters
//   </Button>
// );

// /* legend: one colour per PO, click to highlight */
// export const ProductionOrdersLegend = ({ pos, colorMap, focus, onPick, title = "Production Orders (click one to highlight it)" }) => (
//   <Box sx={{ mt: 2.5, pt: 1.5, borderTop: `1px solid ${THEME.border}` }}>
//     <Typography sx={{ fontSize: 13, fontWeight: 600, mb: 1, color: THEME.text }}>{title}</Typography>
//     <Box sx={{ display: "flex", flexWrap: "wrap", gap: "6px 18px" }}>
//       {pos.map((p) => (
//         <Tooltip key={p.label} arrow title={`${p.part_number}${p.role ? " · " + p.role : ""} · qty ${p.quantity}`}>
//           <Box onClick={() => onPick(focus === p.label ? "" : p.label)}
//             sx={{
//               display: "flex", alignItems: "center", gap: 0.75, fontSize: 12, color: focus === p.label ? THEME.text : THEME.muted,
//               fontWeight: focus === p.label ? 700 : 400, cursor: "pointer", userSelect: "none", opacity: focus && focus !== p.label ? 0.5 : 1,
//             }}>
//             <Box sx={{ width: 13, height: 13, borderRadius: "3px", bgcolor: colorMap[p.label] }} />
//             {p.label === p.production_order ? p.label : `${p.label} = ${p.production_order}`}
//           </Box>
//         </Tooltip>
//       ))}
//     </Box>
//   </Box>
// );

// /* ------------------------------------------------------------------ *
//  *  The Gantt itself - exported so it can be reused / tested with plain data
//  * ------------------------------------------------------------------ */
// export function PoGanttGrid({ data, view = "weekly", range, zoom = 1, availableWidth = 0, focus = "", colorMap }) {
//   const stations = data.stations || [];
//   const rng = range || getRange(view, Date.now());
//   const colors = colorMap || buildColorMap(data);
//   const poInfo = useMemo(() => { const m = {}; (data.meta?.pos || []).forEach((p) => { m[p.label] = p; }); return m; }, [data.meta]);

//   const { dayByDate, first, last } = useMemo(() => {
//     const byDate = new Map();
//     (data.days || []).forEach((d) => { byDate.set(d.date, d); });
//     const dates = Array.from(byDate.keys()).sort();
//     return { dayByDate: byDate, first: dates[0], last: dates[dates.length - 1] };
//   }, [data.days]);

//   // non-working: a holiday the server sent, a day skipped inside the schedule, or a Sunday outside it
//   const isOff = (iso) => {
//     const d = dayByDate.get(iso);
//     if (d) return !!d.is_holiday;
//     if (first && iso > first && iso < last) return true;
//     return new Date(iso + "T00:00:00").getDay() === 0;
//   };
//   const wdText = (iso) => { const d = dayByDate.get(iso); return d ? (d.is_holiday ? "Off" : `WD ${d.working_day_no}`) : ""; };

//   const scale = useMemo(
//     () => buildScale({ view, range: rng, zoom, availableWidth, isOff, wdText }),
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//     [view, rng.start, rng.end, zoom, availableWidth, dayByDate],
//   );

//   // one row per station; a station group (SMT line) is ONE row - its stages are never listed as rows of their own
//   const rows = useMemo(() => stations.map((st) => ({ key: String(st.station_id), row: st })), [stations]);

//   // one bar per PO per working day, at the REAL start / end of its run on this station (po_runs).
//   // A run that goes over a Sunday / holiday is cut there, so those days stay blank.
//   const barsOf = (row) => {
//     const out = [];
//     (row.po_runs || []).forEach((r) => {
//       const rs = new Date(r.start).getTime(), re = new Date(r.end).getTime();
//       if (!(re > rs)) return;
//       for (let day = startOfDay(Math.max(rs, rng.start)); day < Math.min(re, rng.end); day = addDays(day, 1)) {
//         const iso = toDateInput(day);
//         if (isOff(iso)) continue;
//         const ws = day + (scale.windowed ? SHIFT_START : 0) * 3600e3;
//         const we = day + (scale.windowed ? SHIFT_END : 24) * 3600e3;
//         const s = Math.max(rs, ws), e = Math.min(re, we);
//         if (e <= s) continue;
//         const x = scale.toX(s);
//         out.push({ po: r.label, x, w: Math.max(scale.toX(e) - x, 2), s, e, run: { start: rs, end: re }, date: iso });
//       }
//     });
//     out.sort((a, b) => a.s - b.s);                       // bars that overlap in time (parallel machines) are stacked in lanes
//     const laneEnd = [];
//     out.forEach((b) => {
//       let l = laneEnd.findIndex((t) => t <= b.s);
//       if (l < 0) { l = laneEnd.length; laneEnd.push(0); }
//       laneEnd[l] = b.e;
//       b.lane = l;
//     });
//     out.forEach((b) => { b.lanes = Math.max(1, laneEnd.length); });
//     return out;
//   };

//   const bodyH = rows.length * ROW_H;
//   const headH = LAYOUT.headerRow1 + LAYOUT.headerRow2;
//   const now = Date.now();
//   const nowH = new Date(now).getHours() + new Date(now).getMinutes() / 60;
//   const showNow = now >= rng.start && now < rng.end && (!scale.windowed || (nowH >= scale.wStart && nowH <= scale.wEnd));

//   const headCell = (c, top, h, key, extra = {}) => (
//     <Box key={key} sx={{
//       position: "absolute", left: c.x, top, width: c.w, height: h, boxSizing: "border-box", borderLeft: `1px solid ${THEME.gridStrong}`,
//       display: "flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap", overflow: "hidden", fontSize: 12,
//       ...(c.off ? { bgcolor: "#e3e7ee", color: THEME.muted } : {}), ...extra,
//     }}>
//       {c.label}
//       {c.sub && scale.dayW >= 22 ? <Box component="span" sx={{ ml: 0.4, fontSize: 9.5, color: THEME.muted }}>{c.sub}</Box> : null}
//     </Box>
//   );

//   return (
//     <Box sx={{ display: "flex", width: LAYOUT.labelWidth + scale.totalWidth, minWidth: "100%" }}>
//       {/* station labels */}
//       <Box sx={{ position: "sticky", left: 0, zIndex: 3, flex: "0 0 auto", width: LAYOUT.labelWidth, bgcolor: "#fff", borderRight: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
//         <Box sx={{
//           position: "sticky", top: 0, zIndex: 4, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box",
//           display: "flex", alignItems: "flex-end", px: 1.5, pb: 0.75, fontWeight: 700, fontSize: 12.5, color: THEME.text,
//         }}>
//           Station
//         </Box>
//         {rows.map(({ key, row }) => (
//           <Box key={key} sx={{
//             height: ROW_H, boxSizing: "border-box", borderBottom: `1px solid ${THEME.gridSoft}`, display: "flex", alignItems: "center",
//             px: 1.5, gap: 0.5, bgcolor: "#fff",
//           }}>
//             <Tooltip arrow disableHoverListener={!row.step_names} title={row.step_names ? (
//               <Box sx={{ fontSize: 12 }}>
//                 <div><b>Stages in this row</b></div>
//                 {row.step_names.map((n, i) => <div key={i}>{i + 1}. {n}</div>)}
//               </Box>
//             ) : ""}>
//               <Box sx={{ minWidth: 0, flex: 1 }}>
//                 <Box sx={{ fontWeight: 700, fontSize: 12.5, lineHeight: 1.25, color: THEME.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
//                   {row.name}
//                   {row.step_names ? <span style={{ fontWeight: 400, color: THEME.muted }}> ({row.step_names.length} stages)</span> : null}
//                 </Box>
//                 {(row.role || row.part_number) && (
//                   <Box sx={{ fontSize: 10.5, color: THEME.muted, lineHeight: 1.15, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
//                     {[row.role === "CHILD" ? "Child" : row.role === "MAIN" ? "Main" : "", row.part_number].filter(Boolean).join(" · ")}
//                   </Box>
//                 )}
//               </Box>
//             </Tooltip>
//             {row.shifts ? <Box sx={{ fontSize: 11, color: THEME.muted, flex: "0 0 auto" }}>{row.shifts} shift</Box> : null}
//           </Box>
//         ))}
//       </Box>

//       {/* timeline */}
//       <Box sx={{ position: "relative", flex: "0 0 auto", width: scale.totalWidth }}>
//         <Box sx={{ position: "sticky", top: 0, zIndex: 3, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
//           {scale.row1.map((c, i) => headCell(c, 0, LAYOUT.headerRow1, `a${i}`, { fontWeight: 700, borderBottom: `1px solid ${THEME.gridSoft}` }))}
//           {scale.row2.map((c, i) => headCell(c, LAYOUT.headerRow1, LAYOUT.headerRow2, `b${i}`, { borderLeft: `1px solid ${THEME.gridSoft}`, justifyContent: scale.windowed ? "flex-start" : "center", pl: scale.windowed ? 0.5 : 0, fontSize: 11.5 }))}
//         </Box>

//         <Box sx={{ position: "relative", height: bodyH }}>
//           <svg width={scale.totalWidth} height={bodyH} style={{ position: "absolute", left: 0, top: 0 }}>
//             {scale.offDays.map((o, i) => <rect key={`o${i}`} x={o.x} y={0} width={o.w} height={bodyH} fill={THEME.offDay} />)}
//             {scale.grid.map((g, i) => <line key={`g${i}`} x1={g.x + 0.5} x2={g.x + 0.5} y1={0} y2={bodyH} stroke={g.strong ? THEME.gridStrong : THEME.gridSoft} />)}
//             {rows.map((_, i) => <line key={`r${i}`} x1={0} x2={scale.totalWidth} y1={(i + 1) * ROW_H - 0.5} y2={(i + 1) * ROW_H - 0.5} stroke={THEME.gridSoft} />)}
//           </svg>

//           {rows.map(({ key, row }, i) => barsOf(row).map((b, k) => {
//             const dim = !!focus && b.po !== focus;
//             const info = poInfo[b.po];
//             const h = LAYOUT.laneHeight / b.lanes;
//             const cut = b.run.start < b.s || b.run.end > b.e;
//             return (
//               <Tooltip key={`${key}-${k}`} arrow title={
//                 <Box sx={{ fontSize: 12 }}>
//                   <div><b>{row.name}</b></div>
//                   {row.step_names && <div>Stages: {row.step_names.join(" → ")}</div>}
//                   <div>PO: {info && info.label !== info.production_order ? `${b.po} = ${info.production_order}` : b.po}</div>
//                   {info && <div>{info.part_number} · qty {info.quantity}</div>}
//                   <div>{fmtLong(b.date)} · {hm(b.s)} - {hm(b.e)}</div>
//                   {cut && <div>Whole run: {fmtShortDate(b.run.start)} {hm(b.run.start)} → {fmtShortDate(b.run.end)} {hm(b.run.end)}</div>}
//                 </Box>
//               }>
//                 <Box sx={{
//                   position: "absolute", left: b.x, top: i * ROW_H + LAYOUT.barPad + b.lane * h, width: b.w, height: b.lanes > 1 ? h - 1 : h, boxSizing: "border-box",
//                   bgcolor: colors[b.po] || PO_PALETTE[0], color: "#fff", borderRadius: "3px", px: b.w > 20 ? 0.75 : 0, overflow: "hidden",
//                   display: "flex", flexDirection: "column", justifyContent: "center", lineHeight: 1.15, fontSize: 11.5, whiteSpace: "nowrap",
//                   opacity: dim ? 0.25 : 1, boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.35)", cursor: "default",
//                 }}>
//                   {b.w >= 30 && <Box sx={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis" }}>{b.po}</Box>}
//                   {b.lanes === 1 && b.w >= 96 && <Box sx={{ fontSize: 10.5, opacity: 0.92, overflow: "hidden", textOverflow: "ellipsis" }}>{hm(b.s)} - {hm(b.e)}</Box>}
//                 </Box>
//               </Tooltip>
//             );
//           }))}

//           {showNow && <Box sx={{ position: "absolute", left: scale.toX(now), top: 0, width: 2, height: bodyH, bgcolor: THEME.nowLine, zIndex: 2, pointerEvents: "none" }} />}
//         </Box>
//       </Box>
//     </Box>
//   );
// }

// /* ------------------------------------------------------------------ *
//  *  Page
//  * ------------------------------------------------------------------ */
// export default function ScheduleDashboard({ apiBase = DEFAULT_API }) {
//   const [data, setData] = useState(null);
//   const [allPos, setAllPos] = useState([]);            // every yet-to-start PO the backend knows (from the unfiltered load)
//   const [poSel, setPoSel] = useState([]);              // POs to load - click order = load priority
//   const [startDate, setStartDate] = useState("");      // empty = next working day
//   const [timeSource, setTimeSource] = useState("actual");
//   const [labelMode, setLabelMode] = useState("seq");
//   const [showHolidays, setShowHolidays] = useState(false);
//   const [focus, setFocus] = useState("");
//   const [showWarn, setShowWarn] = useState(false);
//   const [showAssume, setShowAssume] = useState(false);
//   const [loading, setLoading] = useState(false);
//   const [exporting, setExporting] = useState(false);
//   const [error, setError] = useState("");
//   const [isFullscreen, setIsFullscreen] = useState(false);
//   const fsRef = useRef(null);

//   /* view / filter state */
//   const [view, setView] = useState("weekly");
//   const [anchor, setAnchor] = useState(() => Date.now());
//   const [customStart, setCustomStart] = useState(null);
//   const [customEnd, setCustomEnd] = useState(null);
//   const [zoom, setZoom] = useState(1);
//   const [stationSel, setStationSel] = useState([]);
//   const [infoAnchor, setInfoAnchor] = useState(null);
//   const [gridEl, setGridEl] = useState(null);
//   const [gridW, setGridW] = useState(0);

//   const authHeaders = () => ({ "x-access-token": localStorage.getItem("token") || "" });   // read at request time
//   const query = () => buildQuery({ pos: poSel, startDate, timeSource, labelMode, showHolidays });

//   useEffect(() => {
//     const onChange = () => setIsFullscreen(!!document.fullscreenElement);
//     document.addEventListener("fullscreenchange", onChange);
//     return () => document.removeEventListener("fullscreenchange", onChange);
//   }, []);
//   const toggleFullscreen = () => {
//     if (document.fullscreenElement) document.exitFullscreen();
//     else if (fsRef.current) fsRef.current.requestFullscreen();
//   };

//   // width of the chart area, so short periods stretch to fill the screen
//   useEffect(() => {
//     if (!gridEl) return undefined;
//     setGridW(gridEl.clientWidth);
//     if (typeof ResizeObserver === "undefined") return undefined;
//     const ro = new ResizeObserver((entries) => setGridW(entries[0].contentRect.width));
//     ro.observe(gridEl);
//     return () => ro.disconnect();
//   }, [gridEl]);

//   const generate = async () => {
//     setLoading(true);
//     setError("");
//     try {
//       const res = await axios.get(`${apiBase}/schedule/po-gantt?${query()}`, { headers: authHeaders() });
//       const d = res.data;
//       if (!d?.stations?.length) {
//         setData(null);
//         setError("No yet-to-start production orders could be scheduled.");
//         return;
//       }
//       const first = d.meta?.start_date || d.days?.[0]?.date;
//       if (first && first !== (data?.meta?.start_date || data?.days?.[0]?.date)) {   // new schedule start -> show it
//         setAnchor(fromDateInput(first));
//         setCustomStart(null);
//         setCustomEnd(null);
//       }
//       setData(d);
//       setFocus("");
//       setStationSel([]);
//       if (!poSel.length) setAllPos(d.meta?.pos || []);       // keep the full list for the PO picker
//     } catch (err) {
//       console.error(err);
//       setData(null);
//       setError(await errorText(err, "Failed to generate the schedule."));
//     } finally {
//       setLoading(false);
//     }
//   };

//   const exportXlsx = async () => {
//     setExporting(true);
//     try {
//       const res = await axios.get(`${apiBase}/schedule/po-gantt/export?${query()}`, { headers: authHeaders(), responseType: "blob" });
//       const url = URL.createObjectURL(res.data);
//       const a = document.createElement("a");
//       a.href = url;
//       a.download = "po_gantt.xlsx";
//       document.body.appendChild(a);
//       a.click();
//       a.remove();
//       URL.revokeObjectURL(url);
//     } catch (err) {
//       setError(await errorText(err, "Export failed."));
//     } finally {
//       setExporting(false);
//     }
//   };

//   /* ---- view controls ---- */
//   const scheduleStart = () => {
//     const first = data?.meta?.start_date || data?.days?.[0]?.date;
//     return first ? fromDateInput(first) : Date.now();
//   };
//   const changeView = (v) => { setView(v); setCustomStart(null); setCustomEnd(null); setZoom(1); };
//   const range = useMemo(() => getRange(view, anchor, customStart, customEnd), [view, anchor, customStart, customEnd]);
//   const navigate = (dir) => setAnchor((a) => shiftAnchor(view, a, dir, range));
//   const zoomIn = () => setZoom((z) => Math.min(ZOOM.max, z + ZOOM.step));
//   const zoomOut = () => setZoom((z) => Math.max(ZOOM.min, z - ZOOM.step));
//   const clearFilters = () => {
//     setStationSel([]);
//     setFocus("");
//     setCustomStart(null);
//     setCustomEnd(null);
//     setZoom(1);
//     setAnchor(scheduleStart());
//   };

//   const meta = data?.meta;
//   const warnings = data?.warnings || [];
//   const assumptions = data?.assumptions || [];
//   const poOptions = allPos.length ? allPos : meta?.pos || [];
//   const colorMap = useMemo(() => buildColorMap(data), [data]);

//   const stationOptions = useMemo(() => Array.from(new Set((data?.stations || []).map((s) => s.name))), [data]);
//   const gridData = useMemo(() => {
//     if (!data) return null;
//     if (!stationSel.length) return data;
//     return { ...data, stations: (data.stations || []).filter((s) => stationSel.includes(s.name)) };
//   }, [data, stationSel]);

//   const poLabelText = (label) => {
//     const p = (meta?.pos || []).find((x) => x.label === label);
//     return p && p.label !== p.production_order ? `${p.label} = ${p.production_order}` : label;
//   };

//   const rangeEndInclusive = addDays(range.end, -1);
//   const hasWorkInRange = useMemo(() => {
//     const a = toDateInput(range.start), b = toDateInput(rangeEndInclusive);
//     return (data?.days || []).some((d) => !d.is_holiday && d.date >= a && d.date <= b);
//   }, [data, range, rangeEndInclusive]);
//   const periodText = `${fmtShortDate(range.start)}${range.end - range.start > DAY ? ` – ${fmtShortDate(rangeEndInclusive)}` : ""}`;

//   return (
//     <Box ref={fsRef} sx={{ p: 2.5, bgcolor: isFullscreen ? "#fff" : "transparent", overflow: "auto", height: isFullscreen ? "100vh" : "auto" }}>
//       <Box sx={{ bgcolor: "#fff", border: `1px solid ${THEME.border}`, borderRadius: "10px", p: 2.5 }}>
//         <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
//           <Typography variant="h6" sx={{ color: "#333", fontWeight: 600 }}>Production Order Schedule - PO on Station</Typography>
//           <Stack direction="row" sx={{ gap: 1 }}>
//             <Button variant="outlined" onClick={exportXlsx} disabled={!data || exporting} sx={{ ...btnSx, borderColor: THEME.primary }}>{exporting ? "Exporting..." : "Export Excel"}</Button>
//             <Button variant="contained" onClick={generate} disabled={loading} sx={{ ...btnSx, bgcolor: THEME.primary, "&:hover": { bgcolor: "#1a5fc7", boxShadow: "none" } }}>{loading ? "Scheduling..." : "Generate Schedule"}</Button>
//           </Stack>
//         </Stack>

//         {/* inputs */}
//         <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 1 }}>
//           <Select
//             size="small" multiple displayEmpty value={poSel}
//             onChange={(e) => setPoSel(typeof e.target.value === "string" ? e.target.value.split(",") : e.target.value)}
//             renderValue={(sel) => (sel.length ? `${sel.length} PO(s): ${sel.join(", ")}` : "All yet-to-start POs")}
//             sx={{ width: 280, ...selectSx }}
//           >
//             {poOptions.length === 0 && <MenuItem disabled value="">Generate once to list the POs</MenuItem>}
//             {poOptions.map((p) => (
//               <MenuItem key={p.production_order} value={p.production_order}>
//                 {p.production_order} - {p.part_number} ({p.quantity})
//               </MenuItem>
//             ))}
//           </Select>
//           <TextField
//             size="small" type="date" label="Start date" InputLabelProps={{ shrink: true }} sx={{ width: 170, ...fieldSx }}
//             value={startDate} onChange={(e) => setStartDate(e.target.value)}
//           />
//           <Select size="small" value={timeSource} onChange={(e) => setTimeSource(e.target.value)} sx={{ minWidth: 150, ...selectSx }}>
//             <MenuItem value="actual">Actual time</MenuItem>
//             <MenuItem value="sap">SAP time</MenuItem>
//           </Select>
//           <Select size="small" value={labelMode} onChange={(e) => setLabelMode(e.target.value)} sx={{ minWidth: 170, ...selectSx }}>
//             <MenuItem value="seq">Labels: B1, B2...</MenuItem>
//             <MenuItem value="po">Labels: PO number</MenuItem>
//           </Select>
//           <FormControlLabel
//             control={<Switch size="small" checked={showHolidays} onChange={(e) => setShowHolidays(e.target.checked)} />}
//             label={<span style={{ fontSize: 13 }}>Show off days</span>}
//           />
//           {poSel.length > 0 && <Button size="small" onClick={() => setPoSel([])}>Load all</Button>}
//         </Stack>
//         <Typography sx={{ fontSize: 12, color: THEME.muted, mb: 1.5, textAlign: "center" }}>
//           POs are loaded in the order you pick them (first picked = first on the line). Press "Generate Schedule" after changing any input.
//         </Typography>

//         {/* view / filter toolbar */}
//         <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 2 }}>
//           <ViewSelect value={view} onChange={changeView} />
//           <Stack direction="row" alignItems="center">
//             <Tooltip title="Previous"><span><IconButton aria-label="Previous" size="small" disabled={!!range.custom} onClick={() => navigate(-1)} sx={toolSx}><PrevIcon fontSize="small" /></IconButton></span></Tooltip>
//             <Tooltip title="Next"><span><IconButton aria-label="Next" size="small" disabled={!!range.custom} onClick={() => navigate(1)} sx={toolSx}><NextIcon fontSize="small" /></IconButton></span></Tooltip>
//           </Stack>
//           <DateRangeField
//             start={customStart || range.start} end={customEnd || rangeEndInclusive}
//             onChange={(s, e) => { setCustomStart(s); setCustomEnd(e); }}
//           />
//           <MultiSelect placeholder="All stations" options={stationOptions} value={stationSel} onChange={setStationSel} width={230} />
//           <SingleSelect
//             placeholder="Highlight PO" options={(meta?.pos || []).map((p) => p.label)} value={focus || null}
//             onChange={(v) => setFocus(v || "")} getLabel={poLabelText} width={200}
//           />
//           <ChartTools
//             zoomIn={zoomIn} zoomOut={zoomOut} isFullscreen={isFullscreen} toggleFullscreen={toggleFullscreen}
//             onInfo={(e) => setInfoAnchor(e.currentTarget)}
//           />
//           <ClearFiltersButton onClick={clearFilters} />
//           <RefreshButton onClick={generate} loading={loading} />
//         </Stack>
//         <InfoPopover anchorEl={infoAnchor} onClose={() => setInfoAnchor(null)} />

//         {loading && <LinearProgress sx={{ mb: 1 }} />}
//         {error && <Alert severity="warning" sx={{ mb: 2 }}><b>Notice:</b> {error}</Alert>}

//         {data ? (
//           <>
//             <Box sx={{ bgcolor: "#f6f8fb", borderRadius: "8px", px: 2, py: 1.25, mb: 2, fontSize: 13, color: "#374151" }}>
//               <b>{meta?.number_of_pos ?? meta?.pos?.length ?? 0}</b> PO(s) loaded - {fmtLong(meta?.start_date)} to <b>{fmtLong(meta?.finish_date)}</b> over{" "}
//               <b>{meta?.working_days ?? (data.days || []).filter((d) => !d.is_holiday).length}</b> working day(s).
//               <Box component="span" sx={{ ml: 1.5, color: THEME.muted }}>Showing {periodText}</Box>
//             </Box>

//             {warnings.length > 0 && (
//               <Alert severity="warning" sx={{ mb: 2 }}
//                 action={<Button color="inherit" size="small" onClick={() => setShowWarn(!showWarn)}>{showWarn ? "Hide" : "Show"}</Button>}>
//                 {warnings.length} warning(s)
//                 <Collapse in={showWarn}>
//                   <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5, maxHeight: 200, overflow: "auto" }}>
//                     {warnings.map((w, i) => <li key={i}>{w}</li>)}
//                   </Box>
//                 </Collapse>
//               </Alert>
//             )}

//             {!hasWorkInRange && (
//               <Alert severity="info" sx={{ mb: 2 }}
//                 action={<Button color="inherit" size="small" onClick={clearFilters}>Go to schedule start</Button>}>
//                 No scheduled work in this period.
//               </Alert>
//             )}

//             {/* gantt */}
//             <Box ref={setGridEl} sx={{ border: `1px solid ${THEME.border}`, borderRadius: "8px", bgcolor: "#fff", overflow: "auto", maxHeight: isFullscreen ? "calc(100vh - 360px)" : "70vh" }}>
//               <PoGanttGrid
//                 data={gridData} view={view} range={range} zoom={zoom} availableWidth={gridW - LAYOUT.labelWidth - 2}
//                 focus={focus} colorMap={colorMap}
//               />
//             </Box>

//             <ProductionOrdersLegend pos={meta?.pos || []} colorMap={colorMap} focus={focus} onPick={setFocus} />

//             {assumptions.length > 0 && (
//               <Box sx={{ mt: 1.5 }}>
//                 <Button size="small" onClick={() => setShowAssume(!showAssume)}>{showAssume ? "Hide" : "Show"} assumptions ({assumptions.length})</Button>
//                 <Collapse in={showAssume}>
//                   <Box component="ul" sx={{ m: 0, pl: 2.5, fontSize: 12, color: "#4b5563" }}>
//                     {assumptions.map((a, i) => <li key={i}>{a}</li>)}
//                   </Box>
//                 </Collapse>
//               </Box>
//             )}

//             <Typography sx={{ fontSize: 12, color: THEME.muted, mt: 1 }}>
//               Each row is a station (child stages first, then main) and each bar a PO, drawn at the exact start and end of its run within the {pad(SHIFT_START)}:00 - {pad(SHIFT_END)}:00 shift.
//               A PO starts a stage only after the previous one is finished; Sundays, 1st / 3rd Saturdays and holidays stay blank.
//               A station group such as the SMT line is one row - hover its name to see the stages inside it.
//             </Typography>
//           </>
//         ) : (
//           !loading && !error && (
//             <Box sx={{ textAlign: "center", p: 6, color: "#666", bgcolor: "#f8f9fa", borderRadius: "8px" }}>
//               Click "Generate Schedule" to load the yet-to-start production orders onto the stations.
//             </Box>
//           )
//         )}
//       </Box>
//     </Box>
//   );
// }













import React, { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
// import axios from "../../AxiosInstance/axiosInstance";
import axios from "axios";
import {
  Alert, Autocomplete, Box, Button, Chip, Collapse, IconButton, LinearProgress, MenuItem, Popover, Stack, TextField,
  Tooltip, Typography,
} from "@mui/material";
import {
  CalendarMonth as CalendarIcon, ZoomIn as ZoomInIcon, ZoomOut as ZoomOutIcon, OpenInFull as FullscreenIcon,
  FullscreenExit as FullscreenExitIcon, InfoOutlined as InfoIcon, Refresh as RefreshIcon, ChevronLeft as PrevIcon,
  ChevronRight as NextIcon, FileDownloadOutlined as DownloadIcon, WarningAmberRounded as WarnIcon,
  ExpandMore as ExpandIcon, KeyboardArrowRight as CollapsedIcon, FilterAltOff as ClearIcon,
} from "@mui/icons-material";

/* ------------------------------------------------------------------ *
 *  Production Schedule - "PO on Station" Gantt
 *
 *  rows  = stations: CHILD processes first, then MAIN processes (each in its flow order).
 *          "SMT LINE" = the 4 TOP SIDE steps as ONE row (they run together inside one working day).
 *  bars  = the real run of a PO on that station (one colour per PO), cut per working day.
 *
 *  Backend (po_gantt_service.py):
 *    GET {apiBase}/schedule/po-gantt          schedule
 *    GET {apiBase}/schedule/po-gantt/orders   yet-to-start POs for the picker
 *    GET {apiBase}/schedule/po-gantt/export   same params, .xlsx
 * ------------------------------------------------------------------ */

const DEFAULT_API = "http://localhost:2002";

/* ---------- look & feel ---------- */
const PO_PALETTE = [
  "#3b5bdb", "#f08c00", "#f2c94c", "#d6336c", "#fab005", "#e03131",
  "#37b24d", "#94d82d", "#22b8cf", "#1c7ed6", "#7048e8", "#0ca678",
];
const THEME = {
  primary: "#1f6fe5", primaryDark: "#1a5fc7", info: "#1b9ae1", dark: "#5b6573", border: "#e3e7ee",
  gridStrong: "#cfd6e0", gridSoft: "#edf0f5", text: "#1f2937", muted: "#6b7280", nowLine: "#ef4444",
  offDay: "rgba(100,116,139,0.09)", headBg: "#f5f7fb", panelBg: "#f8fafc",
};
const SECTIONS = {
  CHILD: { title: "Child processes", color: "#0b7a5c", bg: "#e8f7f1", tag: "Child" },
  MAIN: { title: "Main processes", color: "#1c5fbf", bg: "#e9f1fd", tag: "Main" },
};
const VIEW_MODES = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "yearly", label: "Yearly" },
];
const TIME_SOURCES = [{ value: "actual", label: "Actual time" }, { value: "sap", label: "SAP time" }];
const LABEL_MODES = [{ value: "seq", label: "B1, B2, B3 ..." }, { value: "po", label: "PO number" }];
const LAYOUT = { labelWidth: 290, head1: 30, head2: 26, rowH: 46, sectionH: 30, barPad: 7 };
const BASE_DAY_WIDTH = { daily: 900, weekly: 160, monthly: 46, yearly: 3.2 };   // px per day at zoom = 1
const ZOOM = { min: 0.5, max: 6, step: 0.5 };
const MAX_CUSTOM_RANGE_DAYS = 400;

/* ---------- date helpers ---------- */
const DAY = 24 * 3600 * 1000;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const pad = (n) => String(n).padStart(2, "0");
const toDateInput = (ts) => {
  if (!ts) return "";
  const d = new Date(ts);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const fromDateInput = (s) => {
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d).getTime();
};
const startOfDay = (ts) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); };
const addDays = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n).getTime(); };
const addMonths = (ts, n) => { const d = new Date(ts); return new Date(d.getFullYear(), d.getMonth() + n, 1).getTime(); };
const startOfWeekMon = (ts) => { const d = new Date(startOfDay(ts)); return addDays(d.getTime(), -((d.getDay() + 6) % 7)); };
const fmtShortDate = (ts) => { const d = new Date(ts); return `${pad(d.getDate())} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; };
const fmtLong = (iso) => (iso ? fmtShortDate(fromDateInput(iso)) : "-");
const dayLabel = (ts) => { const d = new Date(ts); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
const hm = (ts) => { const d = new Date(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fmtDateTime = (ts) => `${fmtShortDate(ts)}, ${hm(ts)}`;
const fmtMinutes = (m) => (m >= 60 ? `${Math.floor(m / 60)} h ${pad(Math.round(m % 60))} min` : `${Math.round(m)} min`);

// anchor = any timestamp inside the period being shown
function getRange(view, anchor, customStart, customEnd) {
  if (customStart && customEnd) {
    const s = startOfDay(Math.min(customStart, customEnd));
    let e = addDays(startOfDay(Math.max(customStart, customEnd)), 1);
    if ((e - s) / DAY > MAX_CUSTOM_RANGE_DAYS) e = addDays(s, MAX_CUSTOM_RANGE_DAYS);
    return { start: s, end: e, custom: true };
  }
  switch (view) {
    case "daily": { const s = startOfDay(anchor); return { start: s, end: addDays(s, 1) }; }
    case "weekly": { const s = startOfWeekMon(anchor); return { start: s, end: addDays(s, 7) }; }
    case "monthly": { const s = addMonths(anchor, 0); return { start: s, end: addMonths(s, 1) }; }
    default: { const s = addMonths(anchor, -1); return { start: s, end: addMonths(s, 12) }; }   // yearly
  }
}
function shiftAnchor(view, anchor, dir) {
  switch (view) {
    case "daily": return addDays(anchor, dir);
    case "weekly": return addDays(anchor, 7 * dir);
    case "monthly": return addMonths(anchor, dir);
    default: return addMonths(anchor, 12 * dir);
  }
}

/* ---------- the time axis ----------
 * Daily / Weekly draw only the working window of each day (e.g. 06:00-20:00, from the backend) with hour labels;
 * Monthly / Yearly draw full days. toX converts a timestamp to a pixel x inside the timeline. */
function buildScale({ view, range, zoom, availableWidth, isOff, wdText, windowStart = 6, windowEnd = 20 }) {
  const windowed = view === "daily" || view === "weekly";
  let wStart = windowed ? windowStart : 0;
  let wEnd = windowed ? windowEnd : 24;
  if (wEnd > 24 || wEnd <= wStart) { wStart = 0; wEnd = 24; }
  const hours = wEnd - wStart;

  const days = [];
  for (let t = range.start; t < range.end; t = addDays(t, 1)) days.push(t);

  let baseDay = BASE_DAY_WIDTH[view] || 100;
  if (view === "daily" && days.length > 1) baseDay = BASE_DAY_WIDTH.weekly;
  const fill = Math.max(0, availableWidth) / Math.max(days.length, 1);
  const dayW = Math.max(baseDay, fill) * zoom;
  const totalWidth = dayW * days.length;
  const winStart = (i) => days[i] + wStart * 3600e3;
  const winLen = hours * 3600e3;

  const dayIndexOf = (ts) => {
    if (ts < days[0]) return -1;
    if (ts >= range.end) return days.length;
    let lo = 0, hi = days.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (days[mid] <= ts) lo = mid; else hi = mid - 1; }
    return lo;
  };
  const toX = (ts) => {
    const i = dayIndexOf(ts);
    if (i < 0) return 0;
    if (i >= days.length) return totalWidth;
    const frac = Math.min(1, Math.max(0, (ts - winStart(i)) / winLen));
    return i * dayW + frac * dayW;
  };

  const row1 = [], row2 = [], grid = [];
  const groupBy = (keyFn, labelFn, target) => {
    let startIdx = 0;
    for (let i = 1; i <= days.length; i++) {
      if (i === days.length || keyFn(days[i]) !== keyFn(days[startIdx])) {
        target.push({ x: startIdx * dayW, w: (i - startIdx) * dayW, label: labelFn(days[startIdx], i - startIdx) });
        startIdx = i;
      }
    }
  };
  const hourPx = dayW / hours;

  if (windowed) {
    days.forEach((d, i) => {
      const iso = toDateInput(d);
      const wd = wdText(iso);
      row1.push({
        x: i * dayW, w: dayW, off: isOff(iso),
        label: dayW >= 170 ? `${dayLabel(d)}${wd ? " · " + wd : ""}` : dayW >= 90 ? dayLabel(d) : String(new Date(d).getDate()),
      });
      const step = [1, 2, 3, 4, 6, 12].find((s) => s * hourPx >= 46) || hours;      // hour labels never overlap
      for (let h = wStart; h < wEnd; h += step) {
        const next = Math.min(h + step, wEnd);
        const w = ((next - h) / hours) * dayW;
        row2.push({ x: i * dayW + ((h - wStart) / hours) * dayW, w, label: w >= 38 ? `${pad(h)}:00` : "" });
      }
      if (hourPx >= 6 && days.length <= 31) for (let h = wStart + 1; h < wEnd; h++) grid.push({ x: i * dayW + ((h - wStart) / hours) * dayW, strong: false });
    });
  } else if (view === "monthly" || days.length <= 62) {
    groupBy((t) => `${new Date(t).getFullYear()}-${new Date(t).getMonth()}`, (t) => `${MONTHS_LONG[new Date(t).getMonth()]} ${new Date(t).getFullYear()}`, row1);
    days.forEach((d, i) => row2.push({ x: i * dayW, w: dayW, label: String(new Date(d).getDate()), sub: WEEKDAYS[new Date(d).getDay()][0], off: isOff(toDateInput(d)) }));
  } else {
    groupBy((t) => new Date(t).getFullYear(), (t) => String(new Date(t).getFullYear()), row1);
    groupBy((t) => `${new Date(t).getFullYear()}-${new Date(t).getMonth()}`, (t, n) => (n * dayW < 30 ? MONTHS[new Date(t).getMonth()][0] : MONTHS[new Date(t).getMonth()]), row2);
  }
  if (!windowed) row2.forEach((c) => grid.push({ x: c.x, strong: false }));
  row1.forEach((c) => grid.push({ x: c.x, strong: true }));

  const offDays = [];
  if (dayW >= 12) days.forEach((d, i) => { if (isOff(toDateInput(d))) offDays.push({ x: i * dayW, w: dayW }); });

  return { days, dayW, totalWidth, toX, row1, row2, grid, offDays, windowed, wStart, wEnd };
}

/* ---------- misc ---------- */
const buildQuery = ({ pos, startDate, timeSource, labelMode, showHolidays = true }) => {
  const q = new URLSearchParams();
  pos.forEach((p) => q.append("production_order", p));          // repeated param, order = load priority
  if (startDate) q.append("start_date", startDate);
  q.append("time_source", timeSource);
  q.append("label_mode", labelMode);
  q.append("show_holidays", String(showHolidays));
  return q.toString();
};

const errorText = async (err, fallback) => {
  try {
    let data = err.response?.data;
    if (data instanceof Blob) data = JSON.parse(await data.text());   // export errors arrive as a blob
    const d = data?.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  } catch (_) { /* ignore */ }
  return err.message ? `${fallback} (${err.message})` : fallback;
};

// parse the ISO times once (local time, no offset)
const prepare = (d) => {
  (d?.stations || []).forEach((r) => (r.segments || []).forEach((s) => {
    s._s = Date.parse(s.start); s._e = Date.parse(s.end); s._rs = Date.parse(s.run_start); s._re = Date.parse(s.run_end);
  }));
  return d;
};

// one colour per PO label, in load order
export function buildColorMap(pos) {
  const map = {};
  (pos || []).forEach((p, i) => { map[p.label] = PO_PALETTE[i % PO_PALETTE.length]; });
  return map;
}

// dark text on light bars (yellow / lime), white text on dark bars
const textOn = (hex) => {
  const n = parseInt((hex || "#000000").slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 165 ? "#1f2937" : "#fff";
};

/* ------------------------------------------------------------------ *
 *  Toolbar components
 *  In full screen, menus / popovers must render inside the full-screen element, hence FsContext.
 * ------------------------------------------------------------------ */
const FsContext = createContext(null);
const useFsEl = () => useContext(FsContext);

const fieldSx = {
  "& .MuiOutlinedInput-root": { borderRadius: "6px", fontSize: 13.5, bgcolor: "#fff", minHeight: 38 },
  "& .MuiOutlinedInput-notchedOutline": { borderColor: THEME.border },
  "& .MuiInputLabel-root": { fontSize: 13 },
};
const toolSx = { width: 34, height: 34, color: THEME.primary, "&:hover": { bgcolor: "#eef3fb" } };
const btnSx = { height: 38, textTransform: "none", fontWeight: 600, fontSize: 13.5, boxShadow: "none", whiteSpace: "nowrap", borderRadius: "6px" };

export const SelectField = ({ label, value, onChange, options, width = 150 }) => {
  const fsEl = useFsEl();
  return (
    <TextField select size="small" label={label} value={value} onChange={(e) => onChange(e.target.value)}
      sx={{ width, ...fieldSx }} SelectProps={{ MenuProps: { container: fsEl || undefined } }}>
      {options.map((o) => <MenuItem key={o.value} value={o.value} sx={{ fontSize: 13.5 }}>{o.label}</MenuItem>)}
    </TextField>
  );
};

/* "Start Date - End Date" with calendar button */
export const DateRangeField = ({ start, end, onChange, width = 270 }) => {
  const fsEl = useFsEl();
  const [anchorEl, setAnchorEl] = useState(null);
  const [s, setS] = useState("");
  const [e, setE] = useState("");
  const open = (ev) => { setS(toDateInput(start)); setE(toDateInput(end)); setAnchorEl(ev.currentTarget.closest("[data-daterange]")); };
  const text = start && end ? `${fmtShortDate(start)} – ${fmtShortDate(end)}` : "";

  return (
    <>
      <Box data-daterange sx={{ display: "flex", width }}>
        <TextField size="small" label="Period" placeholder="Start Date – End Date" value={text} onClick={open} fullWidth
          InputLabelProps={{ shrink: true }}
          InputProps={{ readOnly: true, sx: { cursor: "pointer", borderTopRightRadius: 0, borderBottomRightRadius: 0 } }}
          sx={{ ...fieldSx, "& input": { cursor: "pointer" } }} />
        <IconButton aria-label="Pick dates" onClick={open}
          sx={{ width: 40, height: 38, borderRadius: "0 6px 6px 0", bgcolor: THEME.primary, color: "#fff", "&:hover": { bgcolor: THEME.primaryDark } }}>
          <CalendarIcon fontSize="small" />
        </IconButton>
      </Box>
      <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={() => setAnchorEl(null)} container={fsEl || undefined}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
        <Stack spacing={1.5} sx={{ p: 2, width: 260 }}>
          <TextField size="small" type="date" label="Start Date" value={s} onChange={(ev) => setS(ev.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" label="End Date" value={e} onChange={(ev) => setE(ev.target.value)} InputLabelProps={{ shrink: true }} />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" onClick={() => { onChange(null, null); setAnchorEl(null); }}>Clear</Button>
            <Button size="small" variant="contained" disabled={!s || !e}
              onClick={() => { onChange(fromDateInput(s), fromDateInput(e)); setAnchorEl(null); }}>Apply</Button>
          </Stack>
        </Stack>
      </Popover>
    </>
  );
};

/* multi select (Autocomplete) */
export const MultiSelect = ({ label, placeholder, options, value, onChange, width = 200, getLabel = (o) => String(o), renderOption, limitTags = 1 }) => {
  const fsEl = useFsEl();
  return (
    <Autocomplete multiple size="small" limitTags={limitTags} disableCloseOnSelect disablePortal={!!fsEl}
      options={options} value={value} getOptionLabel={getLabel}
      isOptionEqualToValue={(a, b) => getLabel(a) === getLabel(b)}
      onChange={(_, v) => onChange(v)} renderOption={renderOption}
      sx={{ width, ...fieldSx, "& .MuiAutocomplete-inputRoot": { flexWrap: "nowrap", overflow: "hidden" }, "& .MuiAutocomplete-input": { minWidth: "40px !important" } }}
      ChipProps={{ size: "small", sx: { maxWidth: 120, fontSize: 12, height: 22 } }}
      renderInput={(params) => (
        <TextField {...params} label={label} placeholder={value.length ? "" : placeholder}
          InputLabelProps={{ ...params.InputLabelProps, shrink: true }} />
      )} />
  );
};

/* zoom / fullscreen / info */
export const ChartTools = ({ zoomIn, zoomOut, isFullscreen, toggleFullscreen, onInfo }) => (
  <Stack direction="row" spacing={0.25} alignItems="center">
    <Tooltip title="Zoom in"><IconButton aria-label="Zoom in" onClick={zoomIn} sx={toolSx}><ZoomInIcon fontSize="small" /></IconButton></Tooltip>
    <Tooltip title="Zoom out"><IconButton aria-label="Zoom out" onClick={zoomOut} sx={toolSx}><ZoomOutIcon fontSize="small" /></IconButton></Tooltip>
    <Tooltip title={isFullscreen ? "Exit full screen" : "Full screen"}>
      <IconButton aria-label="Full screen" onClick={toggleFullscreen} sx={toolSx}>
        {isFullscreen ? <FullscreenExitIcon fontSize="small" /> : <FullscreenIcon fontSize="small" />}
      </IconButton>
    </Tooltip>
    {onInfo && (
      <Tooltip title="How to read this chart">
        <IconButton aria-label="Info" onClick={onInfo} sx={{ width: 36, height: 36, ml: 0.5, borderRadius: "6px", bgcolor: THEME.info, color: "#fff", "&:hover": { bgcolor: "#1488c9" } }}>
          <InfoIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    )}
  </Stack>
);

export const InfoPopover = ({ anchorEl, onClose, lineGroups }) => {
  const fsEl = useFsEl();
  return (
    <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={onClose} container={fsEl || undefined}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}>
      <Box sx={{ p: 2, width: 350, fontSize: 13, color: THEME.text }}>
        <Typography fontWeight={700} fontSize={14} mb={1}>How to read this chart</Typography>
        <Box component="ul" sx={{ m: 0, pl: 2.25, "& li": { mb: 0.6 } }}>
          <li>Each row is a station. <b>Child processes</b> come first, then <b>main processes</b>, each in the order of the product flow.</li>
          <li>Each bar is a production order (one colour per PO). Hover it for the part, quantity, operation, start and finish.</li>
          {Object.entries(lineGroups || {}).map(([g, steps]) => (
            <li key={g}><b>{g}</b> is one row for {steps.length} steps ({steps.join(", ")}); a PO runs them in one go, within one working day.</li>
          ))}
          <li>Pick a <b>production order</b> or <b>part number</b> to see only the stations it goes through; other POs fade.</li>
          <li>Daily &amp; Weekly show the working hours; Monthly &amp; Yearly show full days. Shaded columns are non-working days; the red line is now.</li>
          <li>Use the &lt; &gt; arrows to move period, the Period field for a custom range, and zoom to stretch the timeline.</li>
        </Box>
      </Box>
    </Popover>
  );
};

/* legend: one colour per PO, click to filter */
export const ProductionOrdersLegend = ({ pos, colorMap, selected, onToggle }) => (
  <Box sx={{ mt: 2, pt: 1.5, borderTop: `1px solid ${THEME.border}` }}>
    <Typography sx={{ fontSize: 13, fontWeight: 600, mb: 1, color: THEME.text }}>
      Production Orders <Box component="span" sx={{ fontWeight: 400, color: THEME.muted }}>(click to show only its stations)</Box>
    </Typography>
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: "8px 18px" }}>
      {pos.map((p) => {
        const on = selected.includes(p.label);
        const faded = selected.length > 0 && !on;
        return (
          <Box key={p.label} onClick={() => onToggle(p.label)} title={`${p.part_number} · ${SECTIONS[p.role]?.tag || p.role} · qty ${p.quantity}`}
            sx={{
              display: "flex", alignItems: "center", gap: 0.75, fontSize: 12, cursor: "pointer", userSelect: "none",
              color: on ? THEME.text : THEME.muted, fontWeight: on ? 700 : 400, opacity: faded ? 0.45 : 1,
            }}>
            <Box sx={{ width: 13, height: 13, borderRadius: "3px", bgcolor: colorMap[p.label] }} />
            {p.label === p.production_order ? p.label : `${p.label} = ${p.production_order}`}
            <Box component="span" sx={{ fontSize: 10.5, color: SECTIONS[p.role]?.color }}>{SECTIONS[p.role]?.tag}</Box>
          </Box>
        );
      })}
    </Box>
  </Box>
);

/* a titled strip that groups a row of controls */
const Panel = ({ title, children, right }) => (
  <Box sx={{ bgcolor: THEME.panelBg, border: `1px solid ${THEME.border}`, borderRadius: "10px", px: 1.75, pt: 1.25, pb: 1.5, mb: 1.5 }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.25 }}>
      <Typography sx={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.8, color: THEME.muted, textTransform: "uppercase" }}>{title}</Typography>
      {right}
    </Stack>
    <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25 }}>{children}</Stack>
  </Box>
);

/* hover card for a bar (one element, positioned at the mouse) */
const HoverCard = ({ hover, colorMap }) => {
  if (!hover) return null;
  const { seg, row, x, y } = hover;
  const w = 300;
  const left = Math.max(8, Math.min(x + 16, window.innerWidth - w - 8));
  const top = Math.max(8, Math.min(y + 16, window.innerHeight - 260));
  const line = (k, v) => (
    <Box sx={{ display: "flex", gap: 1, py: 0.2 }}>
      <Box sx={{ width: 92, flex: "0 0 auto", color: THEME.muted }}>{k}</Box>
      <Box sx={{ fontWeight: 500, minWidth: 0 }}>{v}</Box>
    </Box>
  );
  return (
    <Box sx={{
      position: "fixed", left, top, zIndex: 2000, pointerEvents: "none", width: w, bgcolor: "#fff", border: `1px solid ${THEME.border}`,
      borderRadius: "8px", boxShadow: "0 10px 28px rgba(15,23,42,0.18)", p: 1.25, fontSize: 12, color: THEME.text,
    }}>
      <Stack direction="row" alignItems="center" sx={{ gap: 0.75, mb: 0.75 }}>
        <Box sx={{ width: 12, height: 12, borderRadius: "3px", bgcolor: colorMap[seg.label] }} />
        <Box sx={{ fontWeight: 700, fontSize: 13 }}>{seg.label === seg.po ? seg.po : `${seg.label} · PO ${seg.po}`}</Box>
        <Box sx={{ ml: "auto", fontSize: 10.5, fontWeight: 700, color: SECTIONS[seg.role]?.color, bgcolor: SECTIONS[seg.role]?.bg, px: 0.75, borderRadius: "4px" }}>
          {SECTIONS[seg.role]?.tag}
        </Box>
      </Stack>
      {line("Part number", seg.part)}
      {line("Quantity", `${seg.quantity} pcs`)}
      {line("Station", row.kind === "LINE" ? `${row.name} (${(row.steps || []).length} steps)` : row.name)}
      {row.kind === "LINE" && line("Steps", (row.steps || []).map((s, i) => <div key={s}>{i + 1}. {s}</div>))}
      {row.machines > 1 && line("Machine", seg.machine)}
      {line("This block", `${fmtLong(seg.date)} · ${hm(seg._s)} – ${hm(seg._e)} (${fmtMinutes(seg.minutes)})`)}
      {line("Start", fmtDateTime(seg._rs))}
      {line("Finish (PDC)", fmtDateTime(seg._re))}
    </Box>
  );
};

/* ------------------------------------------------------------------ *
 *  The Gantt itself - exported so it can be reused / tested with plain data
 * ------------------------------------------------------------------ */
export const PoGanttGrid = memo(function PoGanttGrid({
  rows, days, dayWindow, view = "weekly", range, zoom = 1, availableWidth = 0, colorMap, activeLabels,
  collapsed, onToggleSection, onHover,
}) {
  const fsEl = useFsEl();
  const { dayByDate, first, last } = useMemo(() => {
    const byDate = new Map();
    (days || []).forEach((d) => byDate.set(d.date, d));
    const dates = Array.from(byDate.keys()).sort();
    return { dayByDate: byDate, first: dates[0], last: dates[dates.length - 1] };
  }, [days]);

  // non-working: an off day the server sent, a day skipped inside the schedule, or a Sunday outside it
  const isOff = useCallback((iso) => {
    const d = dayByDate.get(iso);
    if (d) return !!d.is_holiday;
    if (first && iso > first && iso < last) return true;
    return new Date(iso + "T00:00:00").getDay() === 0;
  }, [dayByDate, first, last]);
  const wdText = useCallback((iso) => {
    const d = dayByDate.get(iso);
    return d ? (d.is_holiday ? "Off" : `WD ${d.working_day_no}`) : "";
  }, [dayByDate]);

  const scale = useMemo(
    () => buildScale({ view, range, zoom, availableWidth, isOff, wdText, windowStart: dayWindow.start, windowEnd: dayWindow.end }),
    [view, range, zoom, availableWidth, isOff, wdText, dayWindow.start, dayWindow.end],
  );

  // section bands + station rows, with their y position
  const layout = useMemo(() => {
    const list = [];
    let y = 0;
    ["CHILD", "MAIN"].forEach((role) => {
      const rs = rows.filter((r) => r.section === role);
      if (!rs.length) return;
      const open = !collapsed.has(role);
      list.push({ type: "section", key: `s-${role}`, role, count: rs.length, open, y, h: LAYOUT.sectionH });
      y += LAYOUT.sectionH;
      if (open) rs.forEach((r) => { list.push({ type: "row", key: r.row_id, row: r, y, h: LAYOUT.rowH }); y += LAYOUT.rowH; });
    });
    return { list, height: y };
  }, [rows, collapsed]);

  const headH = LAYOUT.head1 + LAYOUT.head2;
  const bodyH = Math.max(layout.height, LAYOUT.rowH);
  const now = Date.now();
  const nowH = new Date(now).getHours() + new Date(now).getMinutes() / 60;
  const showNow = now >= range.start && now < range.end && (!scale.windowed || (nowH >= scale.wStart && nowH <= scale.wEnd));

  const headCell = (c, top, h, key, extra = {}) => (
    <Box key={key} sx={{
      position: "absolute", left: c.x, top, width: c.w, height: h, boxSizing: "border-box", borderLeft: `1px solid ${THEME.gridStrong}`,
      display: "flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap", overflow: "hidden", fontSize: 12, color: THEME.text,
      ...(c.off ? { bgcolor: "#e6eaf0", color: THEME.muted } : {}), ...extra,
    }}>
      {c.label}
      {c.sub && scale.dayW >= 22 ? <Box component="span" sx={{ ml: 0.4, fontSize: 9.5, color: THEME.muted }}>{c.sub}</Box> : null}
    </Box>
  );

  const bars = (it) => {
    const all = it.row.segments || [];
    const segs = all.filter((s) => s._e > range.start && s._s < range.end);
    if (!segs.length) return null;
    const machines = Array.from(new Set(all.map((s) => s.machine_no))).sort((a, b) => a - b);
    const lanes = Math.min(Math.max(machines.length, 1), 3);
    const gap = 2;
    const laneH = (it.h - 2 * LAYOUT.barPad - (lanes - 1) * gap) / lanes;
    return segs.map((s, k) => {
      const x = scale.toX(s._s);
      const w = Math.max(scale.toX(s._e) - x, 2);
      const lane = Math.max(0, machines.indexOf(s.machine_no)) % lanes;
      const color = colorMap[s.label] || PO_PALETTE[0];
      const dim = activeLabels && !activeLabels.has(s.label);
      return (
        <Box key={`${it.key}-${k}`}
          onMouseEnter={(e) => onHover({ seg: s, row: it.row, x: e.clientX, y: e.clientY })}
          onMouseMove={(e) => onHover({ seg: s, row: it.row, x: e.clientX, y: e.clientY })}
          onMouseLeave={() => onHover(null)}
          sx={{
            position: "absolute", left: x, top: it.y + LAYOUT.barPad + lane * (laneH + gap), width: w, height: laneH, boxSizing: "border-box",
            bgcolor: color, color: textOn(color), borderRadius: w > 6 ? "4px" : "1px", px: w > 22 ? 0.75 : 0, overflow: "hidden",
            display: "flex", flexDirection: "column", justifyContent: "center", lineHeight: 1.15, fontSize: 11.5, whiteSpace: "nowrap",
            opacity: dim ? 0.15 : 1, boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.35)", cursor: "default",
            transition: "opacity 120ms, filter 120ms", "&:hover": { filter: "brightness(0.93)", zIndex: 1 },
          }}>
          {w >= 28 && <Box sx={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis" }}>{s.label}</Box>}
          {w >= 100 && laneH >= 26 && <Box sx={{ fontSize: 10.5, opacity: 0.9, overflow: "hidden", textOverflow: "ellipsis" }}>{hm(s._s)} – {hm(s._e)}</Box>}
        </Box>
      );
    });
  };

  return (
    <Box sx={{ display: "flex", width: LAYOUT.labelWidth + scale.totalWidth, minWidth: "100%" }}>
      {/* station labels */}
      <Box sx={{ position: "sticky", left: 0, zIndex: 3, flex: "0 0 auto", width: LAYOUT.labelWidth, bgcolor: "#fff", borderRight: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
        <Box sx={{
          position: "sticky", top: 0, zIndex: 4, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box",
          display: "flex", alignItems: "flex-end", justifyContent: "space-between", px: 1.5, pb: 0.75, fontWeight: 700, fontSize: 12.5, color: THEME.text,
        }}>
          <span>Station</span>
          <Box component="span" sx={{ fontWeight: 500, fontSize: 11, color: THEME.muted }}>shifts · m/c</Box>
        </Box>
        {layout.list.map((it) => (it.type === "section" ? (
          <Box key={it.key} onClick={() => onToggleSection(it.role)} sx={{
            height: it.h, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 0.5, px: 1, cursor: "pointer", userSelect: "none",
            bgcolor: SECTIONS[it.role].bg, borderLeft: `3px solid ${SECTIONS[it.role].color}`, borderBottom: `1px solid ${THEME.gridSoft}`,
            color: SECTIONS[it.role].color, fontSize: 11.5, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase",
          }}>
            {it.open ? <ExpandIcon sx={{ fontSize: 18 }} /> : <CollapsedIcon sx={{ fontSize: 18 }} />}
            {SECTIONS[it.role].title}
            <Box component="span" sx={{ ml: "auto", fontWeight: 500, letterSpacing: 0, textTransform: "none", color: THEME.muted }}>
              {it.count} station{it.count === 1 ? "" : "s"}
            </Box>
          </Box>
        ) : (
          <Box key={it.key} sx={{
            height: it.h, boxSizing: "border-box", borderBottom: `1px solid ${THEME.gridSoft}`, display: "flex", alignItems: "center",
            pl: 1.75, pr: 1.25, gap: 1, borderLeft: `3px solid ${SECTIONS[it.row.section].color}33`,
          }}>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Stack direction="row" alignItems="center" sx={{ gap: 0.75, minWidth: 0 }}>
                <Box sx={{ fontWeight: 700, fontSize: 12.5, lineHeight: 1.25, color: THEME.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {it.row.name}
                </Box>
                {it.row.kind === "LINE" && (
                  <Tooltip arrow placement="right" PopperProps={{ container: fsEl || undefined }} title={
                    <Box sx={{ fontSize: 12 }}>
                      <b>One row for {(it.row.steps || []).length} steps, run in one go within one day:</b>
                      {(it.row.steps || []).map((s, i) => <div key={s}>{i + 1}. {s}</div>)}
                    </Box>
                  }>
                    <Box sx={{ flex: "0 0 auto", fontSize: 10, fontWeight: 700, color: "#7048e8", bgcolor: "#f3f0ff", px: 0.6, py: 0.1, borderRadius: "4px", cursor: "help" }}>
                      LINE · {(it.row.steps || []).length} steps
                    </Box>
                  </Tooltip>
                )}
              </Stack>
              <Box sx={{ fontSize: 10.5, color: THEME.muted, lineHeight: 1.3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {(it.row.part_numbers || []).join(", ")}
                {(it.row.shared_with || []).length > 0 && ` · shared with ${it.row.shared_with.map((r) => SECTIONS[r]?.tag || r).join(", ")}`}
              </Box>
            </Box>
            <Box sx={{ flex: "0 0 auto", textAlign: "right", fontSize: 10.5, color: THEME.muted, lineHeight: 1.35 }}>
              <div>{it.row.shifts} shift</div>
              <div>{it.row.machines} m/c</div>
            </Box>
          </Box>
        )))}
      </Box>

      {/* timeline */}
      <Box sx={{ position: "relative", flex: "0 0 auto", width: scale.totalWidth }}>
        <Box sx={{ position: "sticky", top: 0, zIndex: 2, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
          {scale.row1.map((c, i) => headCell(c, 0, LAYOUT.head1, `a${i}`, { fontWeight: 700, borderBottom: `1px solid ${THEME.gridSoft}` }))}
          {scale.row2.map((c, i) => headCell(c, LAYOUT.head1, LAYOUT.head2, `b${i}`, {
            borderLeft: `1px solid ${THEME.gridSoft}`, justifyContent: scale.windowed ? "flex-start" : "center", pl: scale.windowed ? 0.5 : 0, fontSize: 11.5,
          }))}
        </Box>

        <Box sx={{ position: "relative", height: bodyH }}>
          <svg width={scale.totalWidth} height={bodyH} style={{ position: "absolute", left: 0, top: 0 }}>
            {layout.list.filter((it) => it.type === "section").map((it) => (
              <rect key={`sb${it.role}`} x={0} y={it.y} width={scale.totalWidth} height={it.h} fill={SECTIONS[it.role].bg} />
            ))}
            {scale.offDays.map((o, i) => <rect key={`o${i}`} x={o.x} y={0} width={o.w} height={bodyH} fill={THEME.offDay} />)}
            {scale.grid.map((g, i) => <line key={`g${i}`} x1={g.x + 0.5} x2={g.x + 0.5} y1={0} y2={bodyH} stroke={g.strong ? THEME.gridStrong : THEME.gridSoft} />)}
            {layout.list.map((it) => <line key={`r${it.key}`} x1={0} x2={scale.totalWidth} y1={it.y + it.h - 0.5} y2={it.y + it.h - 0.5} stroke={THEME.gridSoft} />)}
          </svg>

          {layout.list.filter((it) => it.type === "row").map(bars)}

          {showNow && <Box sx={{ position: "absolute", left: scale.toX(now), top: 0, width: 2, height: bodyH, bgcolor: THEME.nowLine, zIndex: 2, pointerEvents: "none" }} />}
        </Box>
      </Box>
    </Box>
  );
});

/* ------------------------------------------------------------------ *
 *  Page
 * ------------------------------------------------------------------ */
export default function ScheduleDashboard({ apiBase = DEFAULT_API }) {
  /* plan inputs (sent to the backend) */
  const [orders, setOrders] = useState([]);            // yet-to-start POs for the picker
  const [poSel, setPoSel] = useState([]);              // POs to plan - pick order = load priority (empty = all)
  const [startDate, setStartDate] = useState("");      // empty = next working day
  const [timeSource, setTimeSource] = useState("actual");
  const [labelMode, setLabelMode] = useState("seq");

  /* result */
  const [data, setData] = useState(null);
  const [appliedQuery, setAppliedQuery] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [showWarn, setShowWarn] = useState(false);
  const [showAssume, setShowAssume] = useState(false);

  /* view / filters (client side) */
  const [view, setView] = useState("weekly");
  const [anchor, setAnchor] = useState(() => Date.now());
  const [customStart, setCustomStart] = useState(null);
  const [customEnd, setCustomEnd] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [stationSel, setStationSel] = useState([]);
  const [partSel, setPartSel] = useState([]);
  const [poFilter, setPoFilter] = useState([]);       // PO labels
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [hover, setHover] = useState(null);
  const [infoAnchor, setInfoAnchor] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [gridEl, setGridEl] = useState(null);
  const [gridW, setGridW] = useState(0);
  const fsRef = useRef(null);

  const authHeaders = () => ({ "x-access-token": localStorage.getItem("token") || "" });   // read at request time
  const query = buildQuery({ pos: poSel.map((o) => o.production_order), startDate, timeSource, labelMode });
  const isDirty = !!data && appliedQuery !== null && appliedQuery !== query;

  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (fsRef.current) fsRef.current.requestFullscreen();
  };

  // width of the chart area, so short periods stretch to fill the screen
  useEffect(() => {
    if (!gridEl) return undefined;
    setGridW(gridEl.clientWidth);
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver((entries) => setGridW(entries[0].contentRect.width));
    ro.observe(gridEl);
    return () => ro.disconnect();
  }, [gridEl]);

  const loadOrders = async () => {
    try {
      const res = await axios.get(`${apiBase}/schedule/po-gantt/orders`, { headers: authHeaders() });
      setOrders(res.data?.orders || []);
    } catch (err) {
      console.error(err);            // the picker falls back to the POs of the last schedule
    }
  };

  const generate = async () => {
    const q = query;
    setLoading(true);
    setError("");
    try {
      const res = await axios.get(`${apiBase}/schedule/po-gantt?${q}`, { headers: authHeaders() });
      const d = prepare(res.data);
      if (!d?.stations?.length) {
        setData(null);
        setError("No yet-to-start production orders could be scheduled.");
        return;
      }
      setData(d);
      setAppliedQuery(q);
      setAnchor(fromDateInput(d.meta?.start_date || d.days?.[0]?.date) || Date.now());   // show the schedule start
      setCustomStart(null);
      setCustomEnd(null);
      setStationSel([]);
      setPartSel([]);
      setPoFilter([]);
      setHover(null);
    } catch (err) {
      console.error(err);
      setData(null);
      setError(await errorText(err, "Failed to generate the schedule."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
    generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const exportXlsx = async () => {
    setExporting(true);
    try {
      const res = await axios.get(`${apiBase}/schedule/po-gantt/export?${appliedQuery || query}`, { headers: authHeaders(), responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = "po_gantt.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(await errorText(err, "Export failed."));
    } finally {
      setExporting(false);
    }
  };

  /* ---- view controls ---- */
  const scheduleStart = () => fromDateInput(data?.meta?.start_date || data?.days?.[0]?.date) || Date.now();
  const changeView = (v) => { setView(v); setCustomStart(null); setCustomEnd(null); setZoom(1); };
  const range = useMemo(() => getRange(view, anchor, customStart, customEnd), [view, anchor, customStart, customEnd]);
  const navigate = (dir) => {
    if (range.custom) { setCustomStart(null); setCustomEnd(null); }
    setAnchor((a) => shiftAnchor(view, range.custom ? range.start : a, dir));
  };
  const goTo = (ts) => { setCustomStart(null); setCustomEnd(null); setAnchor(ts); };
  const zoomIn = () => setZoom((z) => Math.min(ZOOM.max, z + ZOOM.step));
  const zoomOut = () => setZoom((z) => Math.max(ZOOM.min, z - ZOOM.step));
  const clearFilters = () => {
    setStationSel([]);
    setPartSel([]);
    setPoFilter([]);
    setCustomStart(null);
    setCustomEnd(null);
    setZoom(1);
    setAnchor(scheduleStart());
  };
  const toggleSection = useCallback((role) => setCollapsed((prev) => {
    const n = new Set(prev);
    if (n.has(role)) n.delete(role); else n.add(role);
    return n;
  }), []);
  const togglePoFilter = (label) => setPoFilter((prev) => (prev.includes(label) ? prev.filter((x) => x !== label) : [...prev, label]));

  /* ---- derived data ---- */
  const meta = data?.meta;
  const warnings = data?.warnings || [];
  const assumptions = data?.assumptions || [];
  const posMeta = useMemo(() => meta?.pos || [], [meta]);
  const allRows = useMemo(() => data?.stations || [], [data]);
  const colorMap = useMemo(() => buildColorMap(posMeta), [posMeta]);
  const dayWindow = useMemo(() => ({ start: meta?.day_window?.start_hour ?? 6, end: meta?.day_window?.end_hour ?? 20 }), [meta]);

  const orderOptions = useMemo(() => (orders.length ? orders : posMeta.map((p) => ({
    production_order: p.production_order, part_number: p.part_number, quantity: p.quantity, role: p.role,
  }))), [orders, posMeta]);
  const partRole = useMemo(() => Object.fromEntries(posMeta.map((p) => [p.part_number, p.role])), [posMeta]);
  const partOptions = useMemo(() => {
    const parts = Array.from(new Set(posMeta.map((p) => p.part_number)));
    return parts.sort((a, b) => (partRole[a] === partRole[b] ? a.localeCompare(b) : partRole[a] === "CHILD" ? -1 : 1));
  }, [posMeta, partRole]);
  const poOptions = useMemo(() => posMeta.map((p) => p.label), [posMeta]);
  const poText = useCallback((label) => {
    const p = posMeta.find((x) => x.label === label);
    return p && p.label !== p.production_order ? `${p.label} = ${p.production_order}` : label;
  }, [posMeta]);
  const stationOptions = useMemo(() => Array.from(new Set(allRows.map((r) => r.name))), [allRows]);

  // PO / part filter -> only the stations those POs go through; other POs fade
  const filtering = partSel.length > 0 || poFilter.length > 0;
  const activeLabels = useMemo(() => {
    if (!filtering) return null;
    return new Set(posMeta.filter((p) => (!partSel.length || partSel.includes(p.part_number))
      && (!poFilter.length || poFilter.includes(p.label))).map((p) => p.label));
  }, [filtering, posMeta, partSel, poFilter]);
  const visibleRows = useMemo(() => {
    const routeRows = activeLabels ? new Set(posMeta.filter((p) => activeLabels.has(p.label)).flatMap((p) => p.route || [])) : null;
    return allRows.filter((r) => (!routeRows || routeRows.has(r.row_id)) && (!stationSel.length || stationSel.includes(r.name)));
  }, [allRows, posMeta, activeLabels, stationSel]);

  const counts = useMemo(() => ({
    child: posMeta.filter((p) => p.role === "CHILD").length,
    main: posMeta.filter((p) => p.role === "MAIN").length,
  }), [posMeta]);
  const rangeEndInclusive = addDays(range.end, -1);
  const hasWorkInRange = useMemo(
    () => visibleRows.some((r) => (r.segments || []).some((s) => s._e > range.start && s._s < range.end && (!activeLabels || activeLabels.has(s.label)))),
    [visibleRows, range, activeLabels],
  );
  const periodText = `${fmtShortDate(range.start)}${range.end - range.start > DAY ? ` – ${fmtShortDate(rangeEndInclusive)}` : ""}`;
  const granText = view === "daily" || view === "weekly"
    ? (range.end - range.start > 14 * DAY ? "day-wise" : `hour-wise, ${pad(Math.floor(dayWindow.start))}:00 – ${pad(Math.min(24, Math.ceil(dayWindow.end)))}:00`)
    : view === "monthly" ? "day-wise" : "month-wise";

  const fsEl = isFullscreen ? fsRef.current : null;

  return (
    <FsContext.Provider value={fsEl}>
      <Box ref={fsRef} sx={{ p: isFullscreen ? 2 : 2.5, bgcolor: isFullscreen ? "#eef1f6" : "transparent", overflow: "auto", height: isFullscreen ? "100vh" : "auto", boxSizing: "border-box" }}>
        <Box sx={{ bgcolor: "#fff", border: `1px solid ${THEME.border}`, borderRadius: "12px", p: 2.5 }}>
          {/* header */}
          <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" sx={{ gap: 1.5, mb: 2 }}>
            <Box>
              <Typography sx={{ fontSize: 18, fontWeight: 700, color: THEME.text }}>Production Schedule – PO on Station</Typography>
              <Typography sx={{ fontSize: 12.5, color: THEME.muted }}>
                Each PO follows its product flow · child processes first, then main processes
              </Typography>
            </Box>
            <Stack direction="row" sx={{ gap: 1 }}>
              <Button variant="outlined" startIcon={<DownloadIcon />} onClick={exportXlsx} disabled={!data || exporting}
                sx={{ ...btnSx, borderColor: THEME.primary, color: THEME.primary }}>
                {exporting ? "Exporting…" : "Export Excel"}
              </Button>
              <Button variant="contained" startIcon={<RefreshIcon />} onClick={generate} disabled={loading}
                sx={{ ...btnSx, bgcolor: THEME.primary, "&:hover": { bgcolor: THEME.primaryDark, boxShadow: "none" } }}>
                {loading ? "Scheduling…" : "Generate Schedule"}
              </Button>
            </Stack>
          </Stack>

          {/* 1. plan */}
          <Panel title="1 · Plan" right={isDirty && (
            <Chip size="small" color="warning" variant="outlined" label='Inputs changed – press "Generate Schedule"' sx={{ height: 22, fontSize: 11.5 }} />
          )}>
            <MultiSelect
              label="Production orders to plan (pick order = priority)" placeholder="All yet-to-start POs" width={420} limitTags={3}
              options={orderOptions} value={poSel} onChange={setPoSel}
              getLabel={(o) => `${o.production_order} · ${o.part_number}`}
              renderOption={({ key, ...props }, o) => (
                <li key={key ?? o.production_order} {...props}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%", fontSize: 13 }}>
                    <b>{o.production_order}</b>
                    <Box component="span" sx={{ color: THEME.muted }}>{o.part_number} · {o.quantity} pcs</Box>
                    <Box component="span" sx={{ ml: "auto", fontSize: 10.5, fontWeight: 700, color: SECTIONS[o.role]?.color, bgcolor: SECTIONS[o.role]?.bg, px: 0.75, borderRadius: "4px" }}>
                      {SECTIONS[o.role]?.tag || o.role}
                    </Box>
                  </Box>
                </li>
              )}
            />
            <TextField size="small" type="date" label="Start date" InputLabelProps={{ shrink: true }} sx={{ width: 170, ...fieldSx }}
              value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            <SelectField label="Time basis" value={timeSource} onChange={setTimeSource} options={TIME_SOURCES} width={150} />
            <SelectField label="Bar labels" value={labelMode} onChange={setLabelMode} options={LABEL_MODES} width={160} />
            {(poSel.length > 0 || startDate) && (
              <Button size="small" onClick={() => { setPoSel([]); setStartDate(""); }} sx={{ textTransform: "none" }}>Reset</Button>
            )}
          </Panel>

          {/* 2. view & filter (same order as the machine schedule page) */}
          <Panel title="2 · View & filter">
            <SelectField label="View" value={view} onChange={changeView} options={VIEW_MODES} width={120} />
            <DateRangeField start={customStart || range.start} end={customEnd || rangeEndInclusive}
              onChange={(s, e) => { setCustomStart(s); setCustomEnd(e); }} />
            <MultiSelect label="Stations" placeholder="All stations" options={stationOptions} value={stationSel} onChange={setStationSel} width={220} />
            <MultiSelect label="Part number" placeholder="All parts" options={partOptions} value={partSel} onChange={setPartSel} width={210}
              renderOption={({ key, ...props }, pn) => (
                <li key={key ?? pn} {...props}>
                  <Box sx={{ display: "flex", width: "100%", fontSize: 13 }}>
                    {pn}
                    <Box component="span" sx={{ ml: "auto", fontSize: 10.5, fontWeight: 700, color: SECTIONS[partRole[pn]]?.color }}>{SECTIONS[partRole[pn]]?.tag}</Box>
                  </Box>
                </li>
              )} />
            <MultiSelect label="Production order" placeholder="All POs" options={poOptions} value={poFilter} onChange={setPoFilter} width={220} getLabel={poText} />
            <ChartTools zoomIn={zoomIn} zoomOut={zoomOut} isFullscreen={isFullscreen} toggleFullscreen={toggleFullscreen}
              onInfo={(e) => setInfoAnchor(e.currentTarget)} />
            <Button variant="contained" startIcon={<ClearIcon />} onClick={clearFilters}
              sx={{ ...btnSx, bgcolor: THEME.dark, "&:hover": { bgcolor: "#4a5361", boxShadow: "none" } }}>
              Clear Filters
            </Button>
          </Panel>
          <InfoPopover anchorEl={infoAnchor} onClose={() => setInfoAnchor(null)} lineGroups={meta?.line_groups} />

          {loading && <LinearProgress sx={{ mb: 1.5, borderRadius: 1 }} />}
          {error && <Alert severity="warning" sx={{ mb: 2 }}><b>Notice:</b> {error}</Alert>}

          {data ? (
            <>
              {/* summary */}
              <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1, mb: 1.5, fontSize: 13, color: "#374151" }}>
                <Chip size="small" label={<span><b>{meta?.number_of_pos ?? posMeta.length}</b> POs</span>} />
                <Chip size="small" sx={{ bgcolor: SECTIONS.CHILD.bg, color: SECTIONS.CHILD.color }} label={<span><b>{counts.child}</b> child</span>} />
                <Chip size="small" sx={{ bgcolor: SECTIONS.MAIN.bg, color: SECTIONS.MAIN.color }} label={<span><b>{counts.main}</b> main</span>} />
                <Box sx={{ mx: 0.5 }}>
                  {fmtLong(meta?.start_date)} → <b>{fmtLong(meta?.finish_date)}</b> · <b>{meta?.working_days}</b> working day(s)
                </Box>
                <Box sx={{ ml: "auto", display: "flex", gap: 1 }}>
                  {warnings.length > 0 && (
                    <Button size="small" color="warning" startIcon={<WarnIcon />} onClick={() => setShowWarn(!showWarn)} sx={{ textTransform: "none", fontWeight: 600 }}>
                      {warnings.length} warning{warnings.length === 1 ? "" : "s"}
                    </Button>
                  )}
                  {assumptions.length > 0 && (
                    <Button size="small" onClick={() => setShowAssume(!showAssume)} sx={{ textTransform: "none" }}>
                      {showAssume ? "Hide" : "Show"} assumptions
                    </Button>
                  )}
                </Box>
              </Stack>
              <Collapse in={showWarn && warnings.length > 0}>
                <Alert severity="warning" sx={{ mb: 1.5 }} onClose={() => setShowWarn(false)}>
                  <Box component="ul" sx={{ m: 0, pl: 2.25, maxHeight: 180, overflow: "auto" }}>
                    {warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </Box>
                </Alert>
              </Collapse>
              <Collapse in={showAssume}>
                <Box component="ul" sx={{ m: 0, mb: 1.5, pl: 2.5, fontSize: 12, color: "#4b5563", bgcolor: THEME.panelBg, borderRadius: "8px", py: 1, pr: 1.5 }}>
                  {assumptions.map((a, i) => <li key={i}>{a}</li>)}
                </Box>
              </Collapse>

              {/* chart */}
              <Box sx={{ border: `1px solid ${THEME.border}`, borderRadius: "10px", overflow: "hidden", bgcolor: "#fff" }}>
                <Stack direction="row" alignItems="center" sx={{ px: 0.75, py: 0.5, gap: 0.5, borderBottom: `1px solid ${THEME.border}`, bgcolor: "#fff" }}>
                  <Tooltip title="Previous period"><IconButton aria-label="Previous" onClick={() => navigate(-1)} sx={{ ...toolSx, border: `1px solid ${THEME.border}` }}><PrevIcon fontSize="small" /></IconButton></Tooltip>
                  <Box sx={{ flex: 1, textAlign: "center", fontSize: 13, fontWeight: 600, color: THEME.text }}>
                    {periodText} <Box component="span" sx={{ fontWeight: 400, color: THEME.muted }}>· {granText}</Box>
                    {filtering && <Box component="span" sx={{ fontWeight: 400, color: THEME.primary }}> · showing {visibleRows.length} station(s) of the selected PO(s)</Box>}
                  </Box>
                  <Button size="small" onClick={() => goTo(Date.now())} sx={{ textTransform: "none", minWidth: 0 }}>Today</Button>
                  <Button size="small" onClick={() => goTo(scheduleStart())} sx={{ textTransform: "none", minWidth: 0 }}>Schedule start</Button>
                  <Tooltip title="Next period"><IconButton aria-label="Next" onClick={() => navigate(1)} sx={{ ...toolSx, border: `1px solid ${THEME.border}` }}><NextIcon fontSize="small" /></IconButton></Tooltip>
                </Stack>

                {!hasWorkInRange && visibleRows.length > 0 && (
                  <Alert severity="info" sx={{ borderRadius: 0 }}
                    action={<Button color="inherit" size="small" onClick={() => goTo(scheduleStart())}>Go to schedule start</Button>}>
                    No scheduled work in this period.
                  </Alert>
                )}

                {visibleRows.length ? (
                  <Box ref={setGridEl} onScroll={() => hover && setHover(null)}
                    sx={{ overflow: "auto", maxHeight: isFullscreen ? "calc(100vh - 330px)" : "68vh" }}>
                    <PoGanttGrid
                      rows={visibleRows} days={data.days} dayWindow={dayWindow} view={view} range={range} zoom={zoom}
                      availableWidth={Math.max(0, gridW - LAYOUT.labelWidth - 2)} colorMap={colorMap} activeLabels={activeLabels}
                      collapsed={collapsed} onToggleSection={toggleSection} onHover={setHover}
                    />
                  </Box>
                ) : (
                  <Box sx={{ p: 5, textAlign: "center", color: THEME.muted, fontSize: 13 }}>
                    No station matches the filters. <Button size="small" onClick={clearFilters}>Clear filters</Button>
                  </Box>
                )}
              </Box>

              <ProductionOrdersLegend pos={posMeta} colorMap={colorMap} selected={poFilter} onToggle={togglePoFilter} />
              <HoverCard hover={hover} colorMap={colorMap} />
            </>
          ) : (
            !loading && !error && (
              <Box sx={{ textAlign: "center", p: 6, color: "#666", bgcolor: "#f8f9fa", borderRadius: "8px" }}>
                Click "Generate Schedule" to load the production orders onto the stations.
              </Box>
            )
          )}
        </Box>
      </Box>
    </FsContext.Provider>
  );
}