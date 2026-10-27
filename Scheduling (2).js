import React, { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import axios from "../../AxiosInstance/axiosInstance";
import {
  Alert, Autocomplete, Box, Button, Checkbox, Chip, Collapse, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, IconButton, LinearProgress, MenuItem, Popover, Snackbar, Stack, Switch, Tab, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Tabs, TextField, Tooltip, Typography,
} from "@mui/material";
import {
  CalendarMonth as CalendarIcon, ZoomIn as ZoomInIcon, ZoomOut as ZoomOutIcon, OpenInFull as FullscreenIcon,
  FullscreenExit as FullscreenExitIcon, InfoOutlined as InfoIcon, Refresh as RefreshIcon, ChevronLeft as PrevIcon,
  ChevronRight as NextIcon, FileDownloadOutlined as DownloadIcon, WarningAmberRounded as WarnIcon,
  ExpandMore as ExpandIcon, KeyboardArrowRight as CollapsedIcon, FilterAltOff as ClearIcon, EditOutlined as EditIcon,
  SaveOutlined as SaveIcon, AccountTree as ProcessTabIcon, PrecisionManufacturing as MachineIcon,
  CompareArrows as CompareIcon, Star as StarIcon, StarBorder as StarBorderIcon, DeleteOutline as DeleteIcon,
  Build as BuildIcon, LowPriority as ReorderIcon,
} from "@mui/icons-material";

/* ------------------------------------------------------------------ *
 *  Production Schedule
 *    Tab 1  PO on Process      rows = processes (child first, then main), bars = PO runs
 *    Tab 2  PO on Machines     rows = machines (grouped by process), bars = PO runs, hatched = breakdown / PM
 *    Tab 3  Planned vs Actual  saved plan (top lane) vs what operators did (bottom lane)
 *
 *  Backend (po_gantt_service.py):
 *    GET  /schedule/po-gantt, /orders, /plants, /export        schedule
 *    GET/PUT /schedule/part-process-time                       Edit Process Times
 *    POST /schedule/plans   GET /schedule/plans?plant=          save / list plans
 *    PUT  /schedule/plans/{id}/baseline   DELETE /schedule/plans/{id}
 *    GET  /schedule/plans/{id}/compare                          planned vs actual
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
  machine: "#b45309", machineBg: "#fff7e8", machineBorder: "#f0b25a", manual: "#6b7280", manualBg: "#f3f4f6",
  down: "#d63939",
};
const SECTIONS = {
  CHILD: { title: "Child processes", color: "#0b7a5c", bg: "#e8f7f1", tag: "Child" },
  MAIN: { title: "Main processes", color: "#1c5fbf", bg: "#e9f1fd", tag: "Main" },
};
const STATUS = {
  DONE_ON_TIME: { label: "Done on time", color: "#2f9e44", bg: "#ebfbee" },
  DONE_LATE: { label: "Done late", color: "#e03131", bg: "#fff0f0" },
  RUNNING: { label: "In progress", color: "#1c7ed6", bg: "#e7f5ff" },
  RUNNING_LATE: { label: "Running late", color: "#e8590c", bg: "#fff4e6" },
  START_OVERDUE: { label: "Start overdue", color: "#c92a2a", bg: "#fff0f0" },
  UPCOMING: { label: "Upcoming", color: "#868e96", bg: "#f1f3f5" },
};
const STATUS_ORDER = ["DONE_ON_TIME", "DONE_LATE", "RUNNING", "RUNNING_LATE", "START_OVERDUE", "UPCOMING"];
const VIEW_MODES = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "yearly", label: "Yearly" },
];
const TIME_SOURCES = [{ value: "actual", label: "MES time" }, { value: "sap", label: "SAP time" }];
const LABEL_MODES = [{ value: "po", label: "PO number" }, { value: "seq", label: "Batches" }];
const LAYOUT = { labelWidth: 360, head1: 32, head2: 28, groupH: 34, childH: 34, barPad: 7 };
const ROW_H = { process: 54, machine: 50, compare: 66 };
const BASE_DAY_WIDTH = { daily: 900, weekly: 160, monthly: 46, yearly: 3.2 };   // px per day at zoom = 1
const ZOOM = { min: 0.5, max: 6, step: 0.5 };
const MAX_CUSTOM_RANGE_DAYS = 400;
const AUTO_GENERATE_DELAY = 450;          // ms after the last dropdown change
const LIVE_REFRESH_MS = 120000;           // Planned vs Actual auto refresh

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
const fmtLong = (iso) => (iso ? fmtShortDate(fromDateInput(iso.slice(0, 10))) : "-");
const dayLabel = (ts) => { const d = new Date(ts); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
const hm = (ts) => { const d = new Date(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fmtDateTime = (ts) => (ts == null || Number.isNaN(ts) ? "–" : `${fmtShortDate(ts)}, ${hm(ts)}`);
const fmtIso = (iso) => (iso ? fmtDateTime(Date.parse(iso)) : "–");
const fmtMinutes = (m) => {
  const a = Math.abs(m);
  if (a >= 1440) return `${Math.floor(a / 1440)} d ${Math.round((a % 1440) / 60)} h`;
  return a >= 60 ? `${Math.floor(a / 60)} h ${pad(Math.round(a % 60))} min` : `${Math.round(a)} min`;
};
const fmtVariance = (m) => (m == null ? "–" : m > 0 ? `+${fmtMinutes(m)} late` : m < 0 ? `${fmtMinutes(m)} early` : "on time");

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
 * Daily / Weekly draw only the working window of each day (08:00-22:00, from the backend) with hour labels;
 * Monthly / Yearly draw full days. toX converts a timestamp to a pixel x inside the timeline. */
function buildScale({ view, range, zoom, availableWidth, isOff, wdText, windowStart = 8, windowEnd = 22 }) {
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
      const step = [1, 2, 3, 4, 6, 12].find((s) => s * hourPx >= 48) || hours;      // hour labels never overlap
      for (let h = wStart; h < wEnd; h += step) {
        const next = Math.min(h + step, wEnd);
        const w = ((next - h) / hours) * dayW;
        row2.push({ x: i * dayW + ((h - wStart) / hours) * dayW, w, label: w >= 40 ? `${pad(h)}:00` : "" });
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
const buildQuery = ({ pos, startDate, timeSource, labelMode, plant, showHolidays = true }) => {
  const q = new URLSearchParams();
  if (plant) q.append("plant", plant);                         // only POs / machines / times of this plant_code
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

const currentUser = () => {
  try {
    for (const k of ["userName", "username", "userID", "user"]) {
      const v = localStorage.getItem(k);
      if (v && v.length < 80) return v;
    }
  } catch (_) { /* ignore */ }
  return null;
};

// parse the ISO times once (local time, no offset)
const T = (iso) => (iso ? Date.parse(iso) : null);
const prepareSchedule = (d) => {
  const segs = (r) => (r.segments || []).forEach((s) => { s._s = T(s.start); s._e = T(s.end); s._rs = T(s.run_start); s._re = T(s.run_end); });
  const downs = (r) => (r.downtime || []).forEach((e) => { e._s = T(e.start); e._e = T(e.end); });
  (d?.stations || []).forEach((r) => { segs(r); downs(r); });
  (d?.machines || []).forEach((r) => { segs(r); downs(r); });
  return d;
};
const prepareCompare = (d) => {
  (d?.rows || []).forEach((r) => (r.items || []).forEach((i) => {
    i._ps = T(i.planned_start); i._pe = T(i.planned_end); i._as = T(i.actual_start); i._au = T(i.actual_until);
  }));
  if (d) d._now = T(d.now);
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
const alpha = (hex, a) => {
  const n = parseInt((hex || "#000000").slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
const HATCH = (c) => `repeating-linear-gradient(135deg, ${alpha(c, 0.22)} 0 6px, ${alpha(c, 0.08)} 6px 12px)`;
const STRIPES = (c) => `repeating-linear-gradient(135deg, ${c} 0 8px, ${alpha(c, 0.72)} 8px 16px)`;

/* ------------------------------------------------------------------ *
 *  Form controls - bigger, and they stretch to fill their grid cell
 *  In full screen, menus / popovers must render inside the full-screen element, hence FsContext.
 * ------------------------------------------------------------------ */
const FsContext = createContext(null);
const useFsEl = () => useContext(FsContext);

const FIELD_H = 46;
const fieldSx = {
  "& .MuiOutlinedInput-root": { borderRadius: "8px", fontSize: 15, bgcolor: "#fff", minHeight: FIELD_H },
  "& .MuiOutlinedInput-notchedOutline": { borderColor: "#d5dbe5" },
  "& .MuiInputLabel-root": { fontSize: 15 },
  "& .MuiInputLabel-shrink": { fontSize: 14, fontWeight: 600, color: "#4b5563" },
  "& .MuiSelect-select": { py: "11px" },
};
const toolSx = { width: 42, height: 42, color: THEME.primary, "&:hover": { bgcolor: "#eef3fb" } };
const btnSx = { height: FIELD_H, px: 2, textTransform: "none", fontWeight: 600, fontSize: 15, boxShadow: "none", whiteSpace: "nowrap", borderRadius: "8px" };

export const SelectField = ({ label, value, onChange, options, width = "100%", renderValue }) => {
  const fsEl = useFsEl();
  return (
    <TextField select size="small" label={label} value={value} onChange={(e) => onChange(e.target.value)}
      sx={{ width, minWidth: 0, ...fieldSx }} SelectProps={{ MenuProps: { container: fsEl || undefined }, renderValue }}>
      {options.map((o) => <MenuItem key={o.value} value={o.value} sx={{ fontSize: 15, py: 1 }}>{o.node || o.label}</MenuItem>)}
    </TextField>
  );
};

/* "Start Date - End Date" with calendar button */
export const DateRangeField = ({ start, end, onChange, width = "100%" }) => {
  const fsEl = useFsEl();
  const [anchorEl, setAnchorEl] = useState(null);
  const [s, setS] = useState("");
  const [e, setE] = useState("");
  const open = (ev) => { setS(toDateInput(start)); setE(toDateInput(end)); setAnchorEl(ev.currentTarget.closest("[data-daterange]")); };
  const text = start && end ? `${fmtShortDate(start)} – ${fmtShortDate(end)}` : "";

  return (
    <>
      <Box data-daterange sx={{ display: "flex", width, minWidth: 0 }}>
        <TextField size="small" label="Period" placeholder="Start Date – End Date" value={text} onClick={open} fullWidth
          InputLabelProps={{ shrink: true }}
          InputProps={{ readOnly: true, sx: { cursor: "pointer", borderTopRightRadius: 0, borderBottomRightRadius: 0 } }}
          sx={{ ...fieldSx, "& input": { cursor: "pointer" } }} />
        <IconButton aria-label="Pick dates" onClick={open}
          sx={{ width: 48, height: FIELD_H, borderRadius: "0 8px 8px 0", bgcolor: THEME.primary, color: "#fff", "&:hover": { bgcolor: THEME.primaryDark } }}>
          <CalendarIcon />
        </IconButton>
      </Box>
      <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={() => setAnchorEl(null)} container={fsEl || undefined}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}>
        <Stack spacing={1.5} sx={{ p: 2, width: 280 }}>
          <TextField size="small" type="date" label="Start Date" value={s} onChange={(ev) => setS(ev.target.value)} InputLabelProps={{ shrink: true }} sx={fieldSx} />
          <TextField size="small" type="date" label="End Date" value={e} onChange={(ev) => setE(ev.target.value)} InputLabelProps={{ shrink: true }} sx={fieldSx} />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button onClick={() => { onChange(null, null); setAnchorEl(null); }}>Clear</Button>
            <Button variant="contained" disabled={!s || !e}
              onClick={() => { onChange(fromDateInput(s), fromDateInput(e)); setAnchorEl(null); }}>Apply</Button>
          </Stack>
        </Stack>
      </Popover>
    </>
  );
};

/* multi select (Autocomplete) */
export const MultiSelect = ({ label, placeholder, options, value, onChange, width = "100%", getLabel = (o) => String(o), renderOption, limitTags = 2 }) => {
  const fsEl = useFsEl();
  return (
    <Autocomplete multiple size="small" limitTags={limitTags} disableCloseOnSelect disablePortal={!!fsEl}
      options={options} value={value} getOptionLabel={getLabel}
      isOptionEqualToValue={(a, b) => getLabel(a) === getLabel(b)}
      onChange={(_, v) => onChange(v)} renderOption={renderOption}
      sx={{
        width, minWidth: 0, ...fieldSx,
        "& .MuiAutocomplete-inputRoot": { flexWrap: "nowrap", overflow: "hidden", py: "5px !important" },
        "& .MuiAutocomplete-input": { minWidth: "48px !important", fontSize: 15 },
      }}
      ListboxProps={{ sx: { fontSize: 15 } }}
      ChipProps={{ size: "small", sx: { maxWidth: 170, fontSize: 13.5, height: 28 } }}
      renderInput={(params) => (
        <TextField {...params} label={label} placeholder={value.length ? "" : placeholder}
          InputLabelProps={{ ...params.InputLabelProps, shrink: true }} />
      )} />
  );
};

/* zoom / info */
export const ChartTools = ({ zoomIn, zoomOut, onInfo }) => (
  <Stack direction="row" spacing={0.25} alignItems="center" sx={{ justifySelf: "end" }}>
    <Tooltip title="Zoom in"><IconButton aria-label="Zoom in" onClick={zoomIn} sx={toolSx}><ZoomInIcon /></IconButton></Tooltip>
    <Tooltip title="Zoom out"><IconButton aria-label="Zoom out" onClick={zoomOut} sx={toolSx}><ZoomOutIcon /></IconButton></Tooltip>
    {onInfo && (
      <Tooltip title="How to read this chart">
        <IconButton aria-label="Info" onClick={onInfo} sx={{ width: FIELD_H, height: FIELD_H, ml: 0.5, borderRadius: "8px", bgcolor: THEME.info, color: "#fff", "&:hover": { bgcolor: "#1488c9" } }}>
          <InfoIcon />
        </IconButton>
      </Tooltip>
    )}
  </Stack>
);

const INFO = {
  process: [
    "Each row is a process. Child processes come first, then main processes, each in the order of the product flow.",
    "Processes with machines are highlighted in amber (⚙ machine count); manual processes are grey.",
    "Each bar is a production order (one colour per PO). Hover it for part, quantity, machine, start and finish.",
    "A thin red hatched strip under a row means one of its machines is down (breakdown or preventive maintenance).",
  ],
  machine: [
    "Each row is a machine, grouped by the process it serves. A machine used by several processes is shared - it never runs two POs at once.",
    "Red hatched blocks are breakdowns (machine_breakdown_logs) and preventive maintenance days (maintenance_schedules); nothing is scheduled there.",
    "Manual processes (no machine) are only on the PO on Process tab.",
  ],
  reorder: [
    "Drag a PO (or use the arrows) to change its priority. The new order is recalculated with the real scheduler and shown next to the current one.",
    "Child POs are always produced before the main POs they feed; moving a main PO up only changes its priority among the main POs.",
    "Apply new order makes it the schedule on all tabs; Save Plan stores it.",
  ],
  compare: [
    "Top lane of each row = the saved plan (light bar in the PO colour). Bottom lane = what the operators actually did.",
    "Green = done on time, red = done late, blue stripes = in progress, orange stripes = running past the planned finish.",
    "A red dashed plan bar = the planned start has passed and nothing has started yet.",
    "Actual times come from the operator logs; data refreshes every 2 minutes while Live is on.",
  ],
};

export const InfoPopover = ({ anchorEl, onClose, lineGroups, tab }) => {
  const fsEl = useFsEl();
  return (
    <Popover open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={onClose} container={fsEl || undefined}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}>
      <Box sx={{ p: 2.25, width: 400, fontSize: 14, color: THEME.text }}>
        <Typography fontWeight={700} fontSize={15.5} mb={1}>How to read this chart</Typography>
        <Box component="ul" sx={{ m: 0, pl: 2.25, "& li": { mb: 0.75 } }}>
          {(INFO[tab] || []).map((t) => <li key={t}>{t}</li>)}
          {Object.entries(lineGroups || {}).map(([g, steps]) => (
            <li key={g}><b>{g}</b> is one row for {steps.length} steps ({steps.join(", ")}); a PO runs them in one go, within one working day.</li>
          ))}
          <li>Daily &amp; Weekly show the working hours; Monthly &amp; Yearly show full days. Shaded columns are non-working days; the red line is now.</li>
          <li>Every dropdown change rebuilds the schedule automatically.</li>
        </Box>
      </Box>
    </Popover>
  );
};

/* ------------------------------------------------------------------ *
 *  Production Orders ribbon (compact)
 *    one pill per linked set:  [child PO(s) → main PO(s)]   (from meta.pos[].depends_on)
 *    click a PO = only its processes · click the arrow = the whole set · collapse / expand remembered
 * ------------------------------------------------------------------ */
const LEGEND_OPEN_KEY = "poGantt.legendOpen";

// group POs into linked sets (child -> main) with union-find on depends_on
export function buildPoSets(pos) {
  const byPo = new Map(pos.map((p) => [p.production_order || p.po, p]));
  const parent = new Map(pos.map((p) => [p.label, p.label]));
  const find = (x) => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x))); x = parent.get(x); } return x; };
  const union = (a, b) => { const ra = find(a), rb = find(b); if (ra !== rb) parent.set(rb, ra); };
  pos.forEach((p) => (p.depends_on || []).forEach((c) => { const cp = byPo.get(c); if (cp) union(cp.label, p.label); }));
  const order = new Map(pos.map((p, i) => [p.label, i]));
  const sets = new Map();
  pos.forEach((p) => {
    const r = find(p.label);
    if (!sets.has(r)) sets.set(r, []);
    sets.get(r).push(p);
  });
  const linked = [], single = [];
  sets.forEach((members) => {
    members.sort((a, b) => order.get(a.label) - order.get(b.label));
    if (members.length > 1) {
      linked.push({ key: members[0].label, members, first: order.get(members[0].label),
        children: members.filter((m) => m.role === "CHILD"), mains: members.filter((m) => m.role !== "CHILD") });
    } else single.push(members[0]);
  });
  linked.sort((a, b) => a.first - b.first);
  return { linked, single, byPo };
}

const PoChip = ({ p, colorMap, selected, onToggle }) => {
  const on = selected.includes(p.label);
  const po = p.production_order || p.po;
  return (
    <Box component="span" onClick={() => onToggle(p.label)}
      title={`${po} · ${p.part_number || p.part} · ${SECTIONS[p.role]?.tag || p.role} · ${p.quantity} pcs`}
      sx={{
        display: "inline-flex", alignItems: "center", gap: 0.5, px: 0.6, py: 0.15, borderRadius: "5px", cursor: "pointer",
        fontSize: 13, fontWeight: on ? 700 : 500, color: THEME.text, whiteSpace: "nowrap",
        opacity: selected.length > 0 && !on ? 0.4 : 1, bgcolor: on ? alpha(colorMap[p.label] || "#000000", 0.15) : "transparent",
        "&:hover": { bgcolor: alpha(colorMap[p.label] || "#000000", 0.12) },
      }}>
      <Box component="span" sx={{ width: 11, height: 11, borderRadius: "3px", bgcolor: colorMap[p.label], flex: "0 0 auto" }} />
      {p.label === po ? p.label : `${p.label}=${po}`}
    </Box>
  );
};

export const ProductionOrdersLegend = ({ pos, colorMap, selected, onToggle, onSelectSet, extra }) => {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(LEGEND_OPEN_KEY) !== "0"; } catch (_) { return true; }
  });
  const toggleOpen = () => setOpen((v) => {
    try { localStorage.setItem(LEGEND_OPEN_KEY, v ? "0" : "1"); } catch (_) { /* ignore */ }
    return !v;
  });
  const { linked, single } = useMemo(() => buildPoSets(pos || []), [pos]);
  const chips = (list) => list.map((p) => <PoChip key={p.label} p={p} colorMap={colorMap} selected={selected} onToggle={onToggle} />);

  return (
    <Box sx={{ mt: 1.5, border: `1px solid ${THEME.border}`, borderRadius: "10px", px: 1, py: 0.5 }}>
      <Stack direction="row" alignItems="center" flexWrap="wrap" sx={{ gap: 1, minHeight: 36 }}>
        <IconButton size="small" onClick={toggleOpen} aria-label={open ? "Collapse production orders" : "Expand production orders"}>
          {open ? <ExpandIcon /> : <CollapsedIcon />}
        </IconButton>
        <Typography onClick={toggleOpen} sx={{ fontSize: 14, fontWeight: 700, color: THEME.text, cursor: "pointer" }}>Production Orders</Typography>
        <Box sx={{ fontSize: 13, color: THEME.muted }}>{(pos || []).length} POs · {linked.length} child→main set{linked.length === 1 ? "" : "s"}</Box>
        {selected.length > 0 && <Button size="small" onClick={() => onSelectSet([])} sx={{ textTransform: "none", fontSize: 13, py: 0 }}>Show all</Button>}
        <Box sx={{ flex: 1 }} />
        {extra}
      </Stack>
      <Collapse in={open} unmountOnExit>
        <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 0.75, pb: 0.75, pl: 0.5 }}>
          {linked.map((set) => {
            const labels = set.members.map((m) => m.label);
            const all = selected.length === labels.length && labels.every((l) => selected.includes(l));
            return (
              <Stack key={set.key} direction="row" alignItems="center" sx={{
                border: `1px solid ${all ? THEME.primary : THEME.border}`, borderRadius: "7px", px: 0.25, bgcolor: "#fff",
              }}>
                {set.children.length ? chips(set.children) : <Box component="span" sx={{ fontSize: 12, color: THEME.muted, px: 0.5 }}>stock</Box>}
                <Tooltip title={all ? "Show all POs" : "Show only this child → main set"}>
                  <IconButton size="small" onClick={() => onSelectSet(all ? [] : labels)} sx={{ p: 0.25, color: all ? THEME.primary : THEME.muted }}>
                    <NextIcon sx={{ fontSize: 18 }} />
                  </IconButton>
                </Tooltip>
                {chips(set.mains)}
              </Stack>
            );
          })}
          {single.length > 0 && (
            <Stack direction="row" alignItems="center" flexWrap="wrap" sx={{ gap: 0.25, pl: linked.length ? 1 : 0, borderLeft: linked.length ? `1px solid ${THEME.border}` : "none" }}>
              <Box component="span" sx={{ fontSize: 12, color: THEME.muted, mr: 0.25 }}>not linked:</Box>
              {chips(single)}
            </Stack>
          )}
        </Stack>
      </Collapse>
    </Box>
  );
};

const LegendSwatch = ({ sx, children }) => (
  <Stack direction="row" alignItems="center" sx={{ gap: 0.75, fontSize: 13, color: "#4b5563" }}>
    <Box sx={{ width: 22, height: 14, borderRadius: "3px", ...sx }} />{children}
  </Stack>
);

/* the controls panel: rows of a CSS grid that use the full width */
const Panel = ({ title, right, children }) => (
  <Box sx={{ bgcolor: THEME.panelBg, border: `1px solid ${THEME.border}`, borderRadius: "12px", px: 2, pt: 1.5, pb: 2, mb: 2 }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.75, minHeight: 24 }}>
      <Typography sx={{ fontSize: 12.5, fontWeight: 700, letterSpacing: 0.8, color: THEME.muted, textTransform: "uppercase" }}>{title}</Typography>
      {right}
    </Stack>
    {children}
  </Box>
);
const FieldRow = ({ cols, children, divider }) => (
  <Box sx={{
    display: "grid", gap: 1.75, alignItems: "center",
    gridTemplateColumns: { xs: "minmax(0,1fr)", sm: "repeat(2, minmax(0,1fr))", lg: cols },
    ...(divider ? { mt: 2, pt: 2, borderTop: `1px dashed ${THEME.gridStrong}` } : {}),
  }}>
    {children}
  </Box>
);

/* hover card (one element, positioned at the mouse) */
const HoverCard = ({ hover }) => {
  if (!hover?.card) return null;
  const { card, x, y } = hover;
  const w = 340;
  const left = Math.max(8, Math.min(x + 18, window.innerWidth - w - 8));
  const top = Math.max(8, Math.min(y + 18, window.innerHeight - 40 - 22 * (card.lines.length + 2)));
  return (
    <Box sx={{
      position: "fixed", left, top, zIndex: 2000, pointerEvents: "none", width: w, bgcolor: "#fff", border: `1px solid ${THEME.border}`,
      borderRadius: "10px", boxShadow: "0 12px 30px rgba(15,23,42,0.2)", p: 1.5, fontSize: 13, color: THEME.text,
    }}>
      <Stack direction="row" alignItems="center" sx={{ gap: 0.85, mb: 0.85 }}>
        {card.color && <Box sx={{ width: 14, height: 14, borderRadius: "4px", bgcolor: card.color, flex: "0 0 auto" }} />}
        <Box sx={{ fontWeight: 700, fontSize: 14 }}>{card.title}</Box>
        {card.tag && (
          <Box sx={{ ml: "auto", fontSize: 11.5, fontWeight: 700, color: card.tag.color, bgcolor: card.tag.bg, px: 0.85, py: 0.15, borderRadius: "5px", whiteSpace: "nowrap" }}>
            {card.tag.text}
          </Box>
        )}
      </Stack>
      {card.lines.filter(Boolean).map(([k, v]) => (
        <Box key={k} sx={{ display: "flex", gap: 1, py: 0.25 }}>
          <Box sx={{ width: 108, flex: "0 0 auto", color: THEME.muted }}>{k}</Box>
          <Box sx={{ fontWeight: 500, minWidth: 0 }}>{v}</Box>
        </Box>
      ))}
    </Box>
  );
};

const segCard = (s, color, processText, extra = []) => ({
  title: s.label === s.po ? `PO ${s.po}` : `${s.label} · PO ${s.po}`, color,
  tag: { text: SECTIONS[s.role]?.tag, color: SECTIONS[s.role]?.color, bg: SECTIONS[s.role]?.bg },
  lines: [
    ["Part number", s.part], ["Quantity", `${s.quantity} pcs`], ["Process", processText], ...extra,
    ["This block", `${fmtLong(s.date)} · ${hm(s._s)} – ${hm(s._e)} (${fmtMinutes(s.minutes)})`],
    ["Start", fmtDateTime(s._rs)], ["Finish (PDC)", fmtDateTime(s._re)],
  ],
});
const downCard = (e) => ({
  title: e.kind === "PM" ? "Preventive maintenance" : "Machine breakdown", color: THEME.down,
  tag: { text: e.status || (e.kind === "PM" ? "Planned" : "Open"), color: THEME.down, bg: "#fff0f0" },
  lines: [["Machine", `${e.machine_name || e.machine} (${e.machine})`], ["Type", e.label], ["From", fmtDateTime(e._s)], ["Until", fmtDateTime(e._e)],
    e.note ? ["Note", e.note] : null],
});

/* ------------------------------------------------------------------ *
 *  Edit Process Times - machine hours + batch size per part / process (table part_process_time)
 * ------------------------------------------------------------------ */
const sameNum = (a, b) => Number(a || 0) === Number(b || 0);
const cellInput = { "& .MuiOutlinedInput-root": { fontSize: 14, height: 36, bgcolor: "#fff" }, "& input": { textAlign: "right", py: 0 } };

export const ProcessTimeDialog = ({ open, onClose, apiBase, plant, authHeaders, timeSource, onSaved }) => {
  const fsEl = useFsEl();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [parts, setParts] = useState([]);
  const [rows, setRows] = useState([]);
  const [part, setPart] = useState("");
  const [edits, setEdits] = useState({});            // "part|process_id" -> { machine_hours, batch_size } (strings, only changed rows)

  useEffect(() => {
    if (!open) return undefined;
    let alive = true;
    (async () => {
      setLoading(true); setErr(""); setEdits({});
      try {
        const res = await axios.get(`${apiBase}/schedule/part-process-time`, { headers: authHeaders(), params: { plant } });
        if (!alive) return;
        const list = res.data?.parts || [];
        setParts(list);
        setRows(res.data?.rows || []);
        setPart((cur) => (list.some((p) => p.part_no === cur) ? cur : list[0]?.part_no || ""));
      } catch (e) {
        if (alive) setErr(await errorText(e, "Could not load the process times."));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, plant, apiBase]);

  const partRows = useMemo(() => rows.filter((r) => r.part_no === part), [rows, part]);
  const partOptions = useMemo(() => parts.map((p) => ({
    value: p.part_no, label: `${p.part_no} · ${[p.product_type, p.sub_type].filter(Boolean).join(" ")}`,
  })), [parts]);
  const rk = (r) => `${r.part_no}|${r.process_id}`;
  const current = (r) => ({
    machine_hours: edits[rk(r)]?.machine_hours ?? String(r.machine_hours ?? 0),
    batch_size: edits[rk(r)]?.batch_size ?? (r.batch_size ? String(r.batch_size) : ""),
  });
  const setField = (r, field, value) => setEdits((prev) => {
    const entry = { ...current(r), [field]: value };
    const next = { ...prev };
    if (sameNum(entry.machine_hours, r.machine_hours) && sameNum(entry.batch_size, r.batch_size)) delete next[rk(r)];
    else next[rk(r)] = entry;
    return next;
  });
  const invalid = (v, int) => v !== "" && (!Number.isFinite(Number(v)) || Number(v) < 0 || (int && !Number.isInteger(Number(v))));
  const total = (r) => {                      // same rule as the scheduler: (actual | SAP) + machine hours
    const base = [timeSource === "sap" ? r.sap_time : r.actual_time, timeSource === "sap" ? r.actual_time : r.sap_time].find((v) => v > 0);
    const mh = Number(current(r).machine_hours || 0);
    return base == null && !(mh > 0) ? null : (base || 0) + (Number.isFinite(mh) ? mh : 0);
  };
  const fmtH = (v) => (v == null ? "–" : Number(v).toFixed(3));

  const changedKeys = Object.keys(edits);
  const hasInvalid = changedKeys.some((k) => invalid(edits[k].machine_hours, false) || invalid(edits[k].batch_size, true));

  const save = async () => {
    const items = changedKeys.map((k) => {
      const [part_no, pid] = k.split("|");
      const e = edits[k];
      return { part_no, process_id: Number(pid), machine_hours: Number(e.machine_hours || 0), batch_size: e.batch_size ? parseInt(e.batch_size, 10) : null };
    });
    setSaving(true); setErr("");
    try {
      if (items.length) await axios.put(`${apiBase}/schedule/part-process-time`, { plant, items }, { headers: authHeaders() });
      onSaved();
    } catch (e) {
      setErr(await errorText(e, "Could not save the process times."));
    } finally {
      setSaving(false);
    }
  };

  const head = { fontWeight: 700, fontSize: 13.5, bgcolor: THEME.headBg, color: THEME.text, whiteSpace: "nowrap" };
  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="lg" fullWidth container={fsEl || undefined}>
      <DialogTitle sx={{ pb: 0.5 }}>
        <Typography sx={{ fontSize: 19, fontWeight: 700 }}>Edit process times</Typography>
        <Typography sx={{ fontSize: 13.5, color: THEME.muted, fontWeight: 400 }}>
          Plant {plant || "–"} · machine hours are added to the {timeSource === "sap" ? "SAP" : "MES"} time of each process · batch size applies to batch processes
        </Typography>
      </DialogTitle>
      <DialogContent>
        <Stack direction="row" alignItems="center" sx={{ gap: 1.5, my: 1.5 }}>
          <Box sx={{ width: 420 }}><SelectField label="Part number" value={part} onChange={setPart} options={partOptions} /></Box>
          {changedKeys.length > 0 && <Chip color="warning" variant="outlined" label={`${changedKeys.length} unsaved change${changedKeys.length === 1 ? "" : "s"}`} />}
        </Stack>
        {loading && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} />}
        {err && <Alert severity="warning" sx={{ mb: 1.5 }}>{err}</Alert>}
        {!loading && !err && !partRows.length && (
          <Box sx={{ p: 4, textAlign: "center", color: THEME.muted, fontSize: 14 }}>
            {plant ? "No process flow found for this part." : "Select a plant first."}
          </Box>
        )}
        {partRows.length > 0 && (
          <TableContainer sx={{ maxHeight: "52vh", border: `1px solid ${THEME.border}`, borderRadius: "8px" }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={head}>Process</TableCell>
                  <TableCell sx={head}>Type</TableCell>
                  <TableCell sx={head} align="right">SAP time (h)</TableCell>
                  <TableCell sx={head} align="right">MES time (h)</TableCell>
                  <TableCell sx={{ ...head, width: 140 }} align="right">Machine hours</TableCell>
                  <TableCell sx={head} align="right">Total / unit (h)</TableCell>
                  <TableCell sx={{ ...head, width: 130 }} align="right">Batch size</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {partRows.map((r) => {
                  const cur = current(r);
                  const dirty = !!edits[rk(r)];
                  return (
                    <TableRow key={rk(r)} hover sx={dirty ? { bgcolor: "#fff8e6" } : undefined}>
                      <TableCell sx={{ fontSize: 14, fontWeight: 600 }}>{r.process_name}</TableCell>
                      <TableCell sx={{ fontSize: 13, color: r.is_batch ? THEME.primary : THEME.muted }}>{r.is_batch ? "Batch" : "Individual"}</TableCell>
                      <TableCell align="right" sx={{ fontSize: 14, color: THEME.muted }}>{fmtH(r.sap_time)}</TableCell>
                      <TableCell align="right" sx={{ fontSize: 14, color: THEME.muted }}>{fmtH(r.actual_time)}</TableCell>
                      <TableCell align="right">
                        <TextField size="small" type="number" value={cur.machine_hours} sx={cellInput}
                          error={invalid(cur.machine_hours, false)} inputProps={{ min: 0, step: 0.01 }}
                          onChange={(e) => setField(r, "machine_hours", e.target.value)} />
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: 14, fontWeight: 700 }}>{fmtH(total(r))}</TableCell>
                      <TableCell align="right">
                        <Tooltip title={r.is_batch ? "" : "Not a batch process"} placement="left">
                          <span>
                            <TextField size="small" type="number" value={cur.batch_size} sx={cellInput} disabled={!r.is_batch}
                              placeholder={r.is_batch ? "30" : "–"} error={invalid(cur.batch_size, true)} inputProps={{ min: 1, step: 1 }}
                              onChange={(e) => setField(r, "batch_size", e.target.value)} />
                          </span>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
        <Typography sx={{ fontSize: 12.5, color: THEME.muted, mt: 1 }}>
          Machine hours 0 = no addition. Empty batch size = the stage default (30). SAP and MES times are shown for reference only.
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={saving} sx={{ textTransform: "none", fontSize: 15 }}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={saving || loading || hasInvalid}
          sx={{ ...btnSx, bgcolor: THEME.primary, "&:hover": { bgcolor: THEME.primaryDark, boxShadow: "none" } }}>
          {saving ? "Saving…" : changedKeys.length ? "Save & regenerate" : "Close & regenerate"}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

/* ------------------------------------------------------------------ *
 *  Save Plan dialog -> POST /schedule/plans (tables schedule_plan + schedule_plan_item)
 * ------------------------------------------------------------------ */
const SavePlanDialog = ({ open, onClose, onSave, saving, error, summary }) => {
  const fsEl = useFsEl();
  const [name, setName] = useState("");
  const [remarks, setRemarks] = useState("");
  const [baseline, setBaseline] = useState(true);
  useEffect(() => { if (open) { setName(""); setRemarks(""); setBaseline(true); } }, [open]);
  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="sm" fullWidth container={fsEl || undefined}>
      <DialogTitle>
        <Typography sx={{ fontSize: 19, fontWeight: 700 }}>Save scheduled plan</Typography>
        <Typography sx={{ fontSize: 13.5, color: THEME.muted }}>{summary}</Typography>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField label="Plan name" placeholder="e.g. Week 44 plan" value={name} onChange={(e) => setName(e.target.value)} sx={fieldSx} autoFocus />
          <TextField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} sx={fieldSx} multiline minRows={2} />
          <FormControlLabel control={<Checkbox checked={baseline} onChange={(e) => setBaseline(e.target.checked)} />}
            label={<span style={{ fontSize: 15 }}>Use as the <b>baseline</b> for Planned vs Actual</span>} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={saving} sx={{ textTransform: "none", fontSize: 15 }}>Cancel</Button>
        <Button variant="contained" startIcon={<SaveIcon />} disabled={saving} onClick={() => onSave({ name, remarks, set_baseline: baseline })}
          sx={{ ...btnSx, bgcolor: THEME.primary, "&:hover": { bgcolor: THEME.primaryDark, boxShadow: "none" } }}>
          {saving ? "Saving…" : "Save plan"}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

/* ------------------------------------------------------------------ *
 *  GanttGrid - one grid for all three tabs
 *    groups: [{ key, title, color, bg, count, rows }]
 *    row:    { id, title, subtitle, badge, right, accent, tint, height, lanes, laneLabels,
 *              bars: [{ s, e, lane, color, label, sub, variant, dimKey, card }], downs: [{ s, e, card }], downMode,
 *              children: [titles] }   variant: solid | plan | stripes | overdue
 * ------------------------------------------------------------------ */
export const GanttGrid = memo(function GanttGrid({
  groups, days, dayWindow, view = "weekly", range, zoom = 1, availableWidth = 0, activeLabels, collapsed,
  onToggleGroup, onHover, labelTitle = "Process", labelRight = "", nowTs,
}) {
  const fsEl = useFsEl();
  const [openChildren, setOpenChildren] = useState(() => new Set());
  const toggleChildren = (id) => setOpenChildren((prev) => {
    const n = new Set(prev);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });

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

  const layout = useMemo(() => {
    const list = [];
    let y = 0;
    groups.forEach((g) => {
      if (!g.rows.length) return;
      const open = !collapsed.has(g.key);
      list.push({ type: "group", key: `g-${g.key}`, group: g, open, y, h: LAYOUT.groupH });
      y += LAYOUT.groupH;
      if (!open) return;
      g.rows.forEach((r) => {
        const h = r.height || ROW_H.process;
        list.push({ type: "row", key: r.id, row: r, y, h });
        y += h;
        if (r.children?.length && openChildren.has(r.id)) {
          r.children.forEach((c, i) => {
            list.push({ type: "child", key: `${r.id}-c${i}`, row: r, title: c, no: i + 1, y, h: LAYOUT.childH });
            y += LAYOUT.childH;
          });
        }
      });
    });
    return { list, height: y };
  }, [groups, collapsed, openChildren]);

  const headH = LAYOUT.head1 + LAYOUT.head2;
  const bodyH = Math.max(layout.height, 60);
  const now = nowTs || Date.now();
  const nowH = new Date(now).getHours() + new Date(now).getMinutes() / 60;
  const showNow = now >= range.start && now < range.end && (!scale.windowed || (nowH >= scale.wStart && nowH <= scale.wEnd));
  const hoverAt = (card) => (e) => onHover({ card, x: e.clientX, y: e.clientY });

  const headCell = (c, top, h, key, extra = {}) => (
    <Box key={key} sx={{
      position: "absolute", left: c.x, top, width: c.w, height: h, boxSizing: "border-box", borderLeft: `1px solid ${THEME.gridStrong}`,
      display: "flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap", overflow: "hidden", fontSize: 13, color: THEME.text,
      ...(c.off ? { bgcolor: "#e6eaf0", color: THEME.muted } : {}), ...extra,
    }}>
      {c.label}
      {c.sub && scale.dayW >= 22 ? <Box component="span" sx={{ ml: 0.4, fontSize: 10.5, color: THEME.muted }}>{c.sub}</Box> : null}
    </Box>
  );

  const renderDowns = (it) => (it.row.downs || []).filter((d) => d.e > range.start && d.s < range.end).map((d, k) => {
    const x = scale.toX(d.s);
    const w = Math.max(scale.toX(d.e) - x, 3);
    const full = it.row.downMode === "full" && it.type === "row";
    return (
      <Box key={`${it.key}-d${k}`} onMouseEnter={hoverAt(d.card)} onMouseMove={hoverAt(d.card)} onMouseLeave={() => onHover(null)}
        sx={{
          position: "absolute", left: x, width: w, zIndex: full ? 0 : 1,
          top: full ? it.y + 3 : it.y + it.h - 7, height: full ? it.h - 6 : 5,
          background: HATCH(THEME.down), border: full ? `1px solid ${alpha(THEME.down, 0.45)}` : "none", borderRadius: "4px",
          display: "flex", alignItems: "flex-end", justifyContent: "flex-start", overflow: "hidden",
        }}>
        {full && w >= 80 && (
          <Box sx={{ fontSize: 11, fontWeight: 800, color: THEME.down, px: 0.75, pb: 0.25, letterSpacing: 0.4, whiteSpace: "nowrap" }}>
            {d.card?.title === "Preventive maintenance" ? "PM" : "BREAKDOWN"}
          </Box>
        )}
      </Box>
    );
  });

  const renderBars = (it) => {
    const row = it.row;
    const bars = (row.bars || []).filter((b) => b.e > range.start && b.s < range.end);
    if (!bars.length) return null;
    const lanes = Math.max(1, row.lanes || 1);
    const gap = 3;
    const pad = it.type === "child" ? 5 : LAYOUT.barPad;
    const laneH = (it.h - 2 * pad - (lanes - 1) * gap) / lanes;
    return bars.map((b, k) => {
      const x = scale.toX(b.s);
      const w = Math.max(scale.toX(b.e) - x, 3);
      const color = b.color || PO_PALETTE[0];
      const dim = activeLabels && b.dimKey && !activeLabels.has(b.dimKey);
      const v = b.variant || "solid";
      const look = {
        solid: { bgcolor: color, color: textOn(color), boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.35)" },
        plan: { bgcolor: alpha(color, 0.22), color: THEME.text, border: `1.5px solid ${alpha(color, 0.9)}` },
        overdue: { bgcolor: alpha(color, 0.16), color: THEME.text, border: `2px dashed ${STATUS.START_OVERDUE.color}` },
        stripes: { background: STRIPES(color), color: "#fff" },
      }[v];
      const lane = Math.min(lanes - 1, Math.max(0, b.lane || 0));
      return (
        <Box key={`${it.key}-b${k}`} onMouseEnter={hoverAt(b.card)} onMouseMove={hoverAt(b.card)} onMouseLeave={() => onHover(null)}
          sx={{
            position: "absolute", left: x, top: it.y + pad + lane * (laneH + gap), width: w, height: laneH, boxSizing: "border-box",
            borderRadius: w > 6 ? "5px" : "2px", px: w > 24 ? 0.75 : 0, overflow: "hidden", zIndex: 1,
            display: "flex", flexDirection: "column", justifyContent: "center", lineHeight: 1.15, fontSize: 12.5, whiteSpace: "nowrap",
            opacity: dim ? 0.13 : 1, cursor: "default", transition: "opacity 120ms, filter 120ms",
            "&:hover": { filter: "brightness(0.93)", zIndex: 2 }, ...look,
            ...(b.outline ? { boxShadow: `0 0 0 2px ${b.outline}` } : {}),
          }}>
          {w >= 30 && <Box sx={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis" }}>{b.label}</Box>}
          {w >= 110 && laneH >= 28 && b.sub && <Box sx={{ fontSize: 11, opacity: 0.92, overflow: "hidden", textOverflow: "ellipsis" }}>{b.sub}</Box>}
        </Box>
      );
    });
  };

  const badge = (bd) => {
    if (!bd) return null;
    const el = (
      <Box sx={{ flex: "0 0 auto", display: "inline-flex", alignItems: "center", gap: 0.4, fontSize: 11.5, fontWeight: 700, color: bd.color, bgcolor: bd.bg, border: bd.border ? `1px solid ${bd.border}` : "none", px: 0.75, py: 0.15, borderRadius: "5px", cursor: bd.tip ? "help" : "default", whiteSpace: "nowrap" }}>
        {bd.icon}{bd.text}
      </Box>
    );
    return bd.tip ? <Tooltip arrow placement="right" PopperProps={{ container: fsEl || undefined }} title={<Box sx={{ fontSize: 13 }}>{bd.tip}</Box>}>{el}</Tooltip> : el;
  };

  return (
    <Box sx={{ display: "flex", width: LAYOUT.labelWidth + scale.totalWidth, minWidth: "100%" }}>
      {/* labels */}
      <Box sx={{ position: "sticky", left: 0, zIndex: 3, flex: "0 0 auto", width: LAYOUT.labelWidth, bgcolor: "#fff", borderRight: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
        <Box sx={{
          position: "sticky", top: 0, zIndex: 4, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box",
          display: "flex", alignItems: "flex-end", justifyContent: "space-between", px: 1.75, pb: 0.9, fontWeight: 700, fontSize: 14, color: THEME.text,
        }}>
          <span>{labelTitle}</span>
          <Box component="span" sx={{ fontWeight: 500, fontSize: 12, color: THEME.muted }}>{labelRight}</Box>
        </Box>
        {layout.list.map((it) => {
          if (it.type === "group") {
            const g = it.group;
            return (
              <Box key={it.key} onClick={() => onToggleGroup(g.key)} sx={{
                height: it.h, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 0.6, px: 1, cursor: "pointer", userSelect: "none",
                bgcolor: g.bg, borderLeft: `4px solid ${g.color}`, borderBottom: `1px solid ${THEME.gridSoft}`,
                color: g.color, fontSize: 13, fontWeight: 700, letterSpacing: 0.4, textTransform: g.upper === false ? "none" : "uppercase",
              }}>
                {it.open ? <ExpandIcon sx={{ fontSize: 20 }} /> : <CollapsedIcon sx={{ fontSize: 20 }} />}
                <Box sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.title}</Box>
                {g.tag}
                <Box component="span" sx={{ ml: "auto", fontWeight: 500, letterSpacing: 0, textTransform: "none", color: THEME.muted, whiteSpace: "nowrap" }}>{g.countText}</Box>
              </Box>
            );
          }
          if (it.type === "child") {
            return (
              <Box key={it.key} sx={{
                height: it.h, boxSizing: "border-box", borderBottom: `1px solid ${THEME.gridSoft}`, display: "flex", alignItems: "center",
                pl: 5, pr: 1.25, gap: 0.85, bgcolor: "#faf9ff", borderLeft: "4px solid #d0bfff",
              }}>
                <Box sx={{ flex: "0 0 auto", width: 20, height: 20, borderRadius: "50%", bgcolor: "#f3f0ff", color: "#7048e8", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>{it.no}</Box>
                <Box title={it.title} sx={{ fontSize: 12.5, fontWeight: 500, color: THEME.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.title}</Box>
              </Box>
            );
          }
          const r = it.row;
          const hasKids = r.children?.length > 0;
          return (
            <Box key={it.key} sx={{
              height: it.h, boxSizing: "border-box", borderBottom: `1px solid ${THEME.gridSoft}`, display: "flex", alignItems: "center",
              pl: hasKids ? 0.75 : 1.75, pr: 1.25, gap: 1, borderLeft: `4px solid ${r.accent || "transparent"}`, bgcolor: r.tint || "#fff",
            }}>
              {hasKids && (
                <IconButton size="small" aria-label={openChildren.has(r.id) ? "Hide steps" : "Show steps"} onClick={() => toggleChildren(r.id)}
                  sx={{ width: 26, height: 26, mr: -0.5, color: "#7048e8" }}>
                  {openChildren.has(r.id) ? <ExpandIcon /> : <CollapsedIcon />}
                </IconButton>
              )}
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Stack direction="row" alignItems="center" sx={{ gap: 0.75, minWidth: 0 }}>
                  <Box title={r.title} sx={{ fontWeight: 700, fontSize: 13.5, lineHeight: 1.3, color: THEME.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {r.title}
                  </Box>
                  {badge(r.badge)}
                  {badge(r.badge2)}
                </Stack>
                {r.subtitle && (
                  <Box title={typeof r.subtitle === "string" ? r.subtitle : undefined} sx={{ fontSize: 12, color: THEME.muted, lineHeight: 1.35, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {r.subtitle}
                  </Box>
                )}
              </Box>
              {r.laneLabels ? (
                <Box sx={{ flex: "0 0 auto", alignSelf: "stretch", display: "flex", flexDirection: "column", justifyContent: "space-around", py: 0.75, fontSize: 11.5, fontWeight: 700, textAlign: "right" }}>
                  {r.laneLabels.map((l) => <Box key={l.text} sx={{ color: l.color }}>{l.text}</Box>)}
                </Box>
              ) : r.right ? (
                <Box sx={{ flex: "0 0 auto", textAlign: "right", fontSize: 12, color: THEME.muted, lineHeight: 1.4 }}>
                  {r.right.map((l) => <div key={l}>{l}</div>)}
                </Box>
              ) : null}
            </Box>
          );
        })}
      </Box>

      {/* timeline */}
      <Box sx={{ position: "relative", flex: "0 0 auto", width: scale.totalWidth }}>
        <Box sx={{ position: "sticky", top: 0, zIndex: 2, height: headH, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.gridStrong}`, boxSizing: "border-box" }}>
          {scale.row1.map((c, i) => headCell(c, 0, LAYOUT.head1, `a${i}`, { fontWeight: 700, fontSize: 13.5, borderBottom: `1px solid ${THEME.gridSoft}` }))}
          {scale.row2.map((c, i) => headCell(c, LAYOUT.head1, LAYOUT.head2, `b${i}`, {
            borderLeft: `1px solid ${THEME.gridSoft}`, justifyContent: scale.windowed ? "flex-start" : "center", pl: scale.windowed ? 0.5 : 0, fontSize: 12.5,
          }))}
        </Box>

        <Box sx={{ position: "relative", height: bodyH }}>
          <svg width={scale.totalWidth} height={bodyH} style={{ position: "absolute", left: 0, top: 0 }}>
            {layout.list.filter((it) => it.type === "group").map((it) => (
              <rect key={`gb${it.key}`} x={0} y={it.y} width={scale.totalWidth} height={it.h} fill={it.group.bg} />
            ))}
            {layout.list.filter((it) => it.type === "row" && it.row.laneLabels).map((it) => (
              <rect key={`lb${it.key}`} x={0} y={it.y + it.h / 2} width={scale.totalWidth} height={it.h / 2} fill="rgba(15,23,42,0.025)" />
            ))}
            {scale.offDays.map((o, i) => <rect key={`o${i}`} x={o.x} y={0} width={o.w} height={bodyH} fill={THEME.offDay} />)}
            {scale.grid.map((g, i) => <line key={`g${i}`} x1={g.x + 0.5} x2={g.x + 0.5} y1={0} y2={bodyH} stroke={g.strong ? THEME.gridStrong : THEME.gridSoft} />)}
            {layout.list.map((it) => <line key={`r${it.key}`} x1={0} x2={scale.totalWidth} y1={it.y + it.h - 0.5} y2={it.y + it.h - 0.5} stroke={THEME.gridSoft} />)}
          </svg>

          {layout.list.filter((it) => it.type !== "group").map(renderDowns)}
          {layout.list.filter((it) => it.type !== "group").map(renderBars)}

          {showNow && <Box sx={{ position: "absolute", left: scale.toX(now), top: 0, width: 2, height: bodyH, bgcolor: THEME.nowLine, zIndex: 3, pointerEvents: "none" }} />}
        </Box>
      </Box>
    </Box>
  );
});

/* ------------------------------------------------------------------ *
 *  Reorder tab - change the priority of the scheduled POs.
 *  Every change is previewed with the real scheduler (machine breakdowns / maintenance, holidays, shifts,
 *  child-before-main) through GET /schedule/po-gantt?production_order=...(new order). "Apply" makes it the schedule.
 * ------------------------------------------------------------------ */
const REORDER_COLS = "28px 36px minmax(150px,1.3fr) minmax(170px,1.4fr) 64px minmax(220px,1.6fr) minmax(220px,1.6fr) 110px 104px";

export const ReorderPanel = ({ data, apiBase, authHeaders, plant, startDate, timeSource, labelMode, colorMap, onApply }) => {
  const current = useMemo(() => data?.meta?.pos || [], [data]);
  const curOrder = useMemo(() => current.map((p) => p.production_order), [current]);
  const curKey = curOrder.join("|");
  const byPo = useMemo(() => Object.fromEntries(current.map((p) => [p.production_order, p])), [current]);

  const [order, setOrder] = useState(curOrder);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [drag, setDrag] = useState(null);             // for styling
  const dragRef = useRef(null);                       // for the drop (state may not be updated yet)
  const [over, setOver] = useState(null);
  const req = useRef(0);
  const orderKey = order.join("|");
  const dirty = orderKey !== curKey;

  useEffect(() => { setOrder(curOrder); setPreview(null); setErr(""); /* new schedule -> start from it */ }, [curKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                                   // preview the new order with the real scheduler
    if (!dirty) { setPreview(null); setErr(""); setLoading(false); return undefined; }
    const t = setTimeout(async () => {
      const id = ++req.current;
      setLoading(true); setErr("");
      try {
        const res = await axios.get(`${apiBase}/schedule/po-gantt?${buildQuery({ pos: order, startDate, timeSource, labelMode, plant })}`, { headers: authHeaders() });
        if (id === req.current) setPreview(res.data);
      } catch (e) {
        if (id === req.current) { setPreview(null); setErr(await errorText(e, "Could not recalculate the new order.")); }
      } finally {
        if (id === req.current) setLoading(false);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [orderKey, dirty]); // eslint-disable-line react-hooks/exhaustive-deps

  const prevByPo = useMemo(() => Object.fromEntries((preview?.meta?.pos || []).map((p) => [p.production_order, p])), [preview]);
  // child -> main links of the order on screen (they change with the order: child PCBs go to the mains first-come-first-served)
  const linkPos = dirty && preview ? preview.meta.pos : current;
  const dependsOn = useMemo(() => Object.fromEntries(linkPos.map((p) => [p.production_order, p.depends_on || []])), [linkPos]);
  const feeds = useMemo(() => {
    const m = {};
    linkPos.forEach((p) => (p.depends_on || []).forEach((c) => { (m[c] = m[c] || []).push(p.production_order); }));
    return m;
  }, [linkPos]);
  const move = (from, to) => setOrder((o) => {
    if (from === to || from == null || to == null || to < 0 || to >= o.length) return o;
    const n = [...o];
    const [x] = n.splice(from, 1);
    n.splice(to, 0, x);
    return n;
  });

  const curFinish = data?.meta?.finish_date;
  const newFinish = preview?.meta?.finish_date;
  const deltas = order.map((po) => {
    const a = byPo[po], b = prevByPo[po];
    return a && b ? (Date.parse(b.end) - Date.parse(a.end)) / 60000 : null;
  });
  const earlier = deltas.filter((d) => d != null && d < -1).length;
  const later = deltas.filter((d) => d != null && d > 1).length;
  const fmtDelta = (d) => (d == null ? "–" : Math.abs(d) <= 1 ? "same" : `${d > 0 ? "+" : "−"}${fmtMinutes(d)}`);
  const head = { fontSize: 12.5, fontWeight: 700, color: THEME.muted, textTransform: "uppercase", letterSpacing: 0.4 };

  if (!current.length) return null;
  return (
    <Box>
      <Stack direction="row" alignItems="center" flexWrap="wrap" sx={{ gap: 1.5, mb: 1.5 }}>
        <Typography sx={{ fontSize: 14.5, color: "#374151" }}>
          Drag the rows (or use the arrows) to change the priority. Machine breakdowns / maintenance, holidays, shifts and
          child-before-main are applied automatically.
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Button onClick={() => setOrder(curOrder)} disabled={!dirty} sx={{ ...btnSx, color: THEME.dark }}>Reset</Button>
        <Button variant="contained" onClick={() => onApply(order)} disabled={!dirty || loading || !!err || !preview}
          sx={{ ...btnSx, bgcolor: THEME.primary, "&:hover": { bgcolor: THEME.primaryDark, boxShadow: "none" } }}>
          Apply new order
        </Button>
      </Stack>

      <Stack direction="row" alignItems="center" flexWrap="wrap" sx={{ gap: 1.25, mb: 1.5, fontSize: 14.5, minHeight: 32 }}>
        <Box>Schedule finish: <b>{fmtLong(curFinish)}</b>{dirty && <> → <b style={{ color: newFinish && newFinish > curFinish ? STATUS.DONE_LATE.color : newFinish && newFinish < curFinish ? STATUS.DONE_ON_TIME.color : THEME.text }}>{loading ? "…" : fmtLong(newFinish)}</b></>}</Box>
        {dirty && preview && !loading && (
          <>
            <Chip size="small" sx={{ bgcolor: STATUS.DONE_ON_TIME.bg, color: STATUS.DONE_ON_TIME.color, fontWeight: 600 }} label={`${earlier} earlier`} />
            <Chip size="small" sx={{ bgcolor: STATUS.DONE_LATE.bg, color: STATUS.DONE_LATE.color, fontWeight: 600 }} label={`${later} later`} />
          </>
        )}
        {loading && <Typography sx={{ fontSize: 13.5, color: THEME.primary, fontWeight: 600 }}>Recalculating…</Typography>}
        {!dirty && <Typography sx={{ fontSize: 13.5, color: THEME.muted }}>Current order of the schedule.</Typography>}
      </Stack>
      {err && <Alert severity="warning" sx={{ mb: 1.5 }}>{err}</Alert>}

      <Box sx={{ border: `1px solid ${THEME.border}`, borderRadius: "10px", overflow: "auto", maxHeight: "calc(100vh - 360px)" }}>
        <Box sx={{ minWidth: 1100 }}>
          <Box sx={{ display: "grid", gridTemplateColumns: REORDER_COLS, gap: 1, alignItems: "center", px: 1.25, py: 1, bgcolor: THEME.headBg, borderBottom: `1px solid ${THEME.border}`, position: "sticky", top: 0, zIndex: 1 }}>
            <span /><Box sx={head}>#</Box><Box sx={head}>Production order</Box><Box sx={head}>Part · link</Box><Box sx={head}>Qty</Box>
            <Box sx={head}>Current start → finish</Box><Box sx={head}>New start → finish</Box><Box sx={head}>Finish change</Box><span />
          </Box>
          {order.map((po, i) => {
            const p = byPo[po] || {};
            const n = prevByPo[po];
            const d = deltas[i];
            const moved = curOrder.indexOf(po) !== i;
            const link = p.role === "CHILD"
              ? (feeds[po] ? `→ ${feeds[po].join(", ")}` : "")
              : ((dependsOn[po] || []).length ? `← ${dependsOn[po].join(", ")}` : "");
            return (
              <Box key={po} draggable
                onDragStart={(e) => { dragRef.current = i; setDrag(i); e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", po); } catch (_) { /* ignore */ } }}
                onDragOver={(e) => { e.preventDefault(); if (over !== i) setOver(i); }}
                onDragLeave={() => setOver((o) => (o === i ? null : o))}
                onDrop={(e) => { e.preventDefault(); move(dragRef.current, i); dragRef.current = null; setDrag(null); setOver(null); }}
                onDragEnd={() => { dragRef.current = null; setDrag(null); setOver(null); }}
                sx={{
                  display: "grid", gridTemplateColumns: REORDER_COLS, gap: 1, alignItems: "center", px: 1.25, py: 0.9, fontSize: 14,
                  borderBottom: `1px solid ${THEME.gridSoft}`, bgcolor: drag === i ? "#eef3fb" : moved ? "#fffbea" : "#fff",
                  borderTop: over === i && drag !== null && drag !== i ? `2px solid ${THEME.primary}` : "2px solid transparent",
                  opacity: drag === i ? 0.6 : 1, cursor: "grab", "&:hover": { bgcolor: drag === i ? "#eef3fb" : "#f8fafc" },
                }}>
                <Box sx={{ color: "#adb5bd", fontSize: 18, lineHeight: 1, userSelect: "none" }} title="Drag to move">⋮⋮</Box>
                <Box sx={{ fontWeight: 700, color: moved ? "#b45309" : THEME.muted }}>{i + 1}</Box>
                <Stack direction="row" alignItems="center" sx={{ gap: 0.75, minWidth: 0 }}>
                  <Box sx={{ width: 12, height: 12, borderRadius: "3px", bgcolor: colorMap[p.label], flex: "0 0 auto" }} />
                  <b>{po}</b>
                  <Box component="span" sx={{ fontSize: 11.5, fontWeight: 700, color: SECTIONS[p.role]?.color }}>{SECTIONS[p.role]?.tag}</Box>
                </Stack>
                <Box sx={{ minWidth: 0, lineHeight: 1.3 }}>
                  <Box sx={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.part_number}</Box>
                  {link && <Box sx={{ fontSize: 12, color: THEME.muted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={p.role === "CHILD" ? "feeds main PO" : "waits for child PO"}>{link}</Box>}
                </Box>
                <Box>{p.quantity}</Box>
                <Box sx={{ color: "#4b5563", whiteSpace: "nowrap" }}>{fmtIso(p.start)} → {fmtIso(p.end)}</Box>
                <Box sx={{ whiteSpace: "nowrap", color: n ? THEME.text : THEME.muted }}>{dirty ? (n ? <>{fmtIso(n.start)} → <b>{fmtIso(n.end)}</b></> : loading ? "…" : "–") : "–"}</Box>
                <Box sx={{ fontWeight: 700, whiteSpace: "nowrap", color: d == null || Math.abs(d) <= 1 ? THEME.muted : d > 0 ? STATUS.DONE_LATE.color : STATUS.DONE_ON_TIME.color }}>{dirty ? fmtDelta(d) : "–"}</Box>
                <Stack direction="row" sx={{ gap: 0 }}>
                  <Tooltip title="Move to top"><span><IconButton size="small" disabled={i === 0} onClick={() => move(i, 0)}><Box component="span" sx={{ fontSize: 15, fontWeight: 800, lineHeight: 1 }}>⤒</Box></IconButton></span></Tooltip>
                  <Tooltip title="Up"><span><IconButton size="small" disabled={i === 0} onClick={() => move(i, i - 1)}><ExpandIcon sx={{ transform: "rotate(180deg)" }} /></IconButton></span></Tooltip>
                  <Tooltip title="Down"><span><IconButton size="small" disabled={i === order.length - 1} onClick={() => move(i, i + 1)}><ExpandIcon /></IconButton></span></Tooltip>
                </Stack>
              </Box>
            );
          })}
        </Box>
      </Box>
      {(preview?.warnings || []).length > 0 && dirty && (
        <Typography sx={{ mt: 1, fontSize: 13, color: THEME.muted }}>{preview.warnings.length} scheduler note(s) for the new order - see warnings after applying.</Typography>
      )}
    </Box>
  );
};

/* ---------- KPI card (Planned vs Actual) ---------- */
const KpiCard = ({ label, value, color, bg, active, onClick }) => (
  <Box onClick={onClick} sx={{
    cursor: onClick ? "pointer" : "default", userSelect: "none", borderRadius: "12px", px: 2, py: 1.5,
    bgcolor: bg || "#fff", border: `1.5px solid ${active ? color : THEME.border}`, boxShadow: active ? `0 0 0 3px ${alpha(color, 0.15)}` : "none",
    transition: "box-shadow 120ms, border-color 120ms", "&:hover": onClick ? { borderColor: color } : {},
  }}>
    <Box sx={{ fontSize: 28, fontWeight: 800, color, lineHeight: 1.1 }}>{value}</Box>
    <Box sx={{ fontSize: 13.5, fontWeight: 600, color: "#4b5563", mt: 0.25 }}>{label}</Box>
  </Box>
);

const StatusChip = ({ status, small }) => {
  const s = STATUS[status] || STATUS.UPCOMING;
  return <Box component="span" sx={{ display: "inline-block", fontSize: small ? 11.5 : 12.5, fontWeight: 700, color: s.color, bgcolor: s.bg, border: `1px solid ${alpha(s.color, 0.3)}`, px: 0.9, py: 0.2, borderRadius: "6px", whiteSpace: "nowrap" }}>{s.label}</Box>;
};

/* ------------------------------------------------------------------ *
 *  Page
 * ------------------------------------------------------------------ */
export default function ScheduleDashboard({ apiBase = DEFAULT_API }) {
  const [tab, setTab] = useState(0);                   // 0 process, 1 machines, 2 planned vs actual

  /* plan inputs (sent to the backend) */
  const [plants, setPlants] = useState([]);
  const [plant, setPlant] = useState("");
  const [plantsReady, setPlantsReady] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [orders, setOrders] = useState([]);            // yet-to-start POs for the picker
  const [poSel, setPoSel] = useState([]);              // POs to plan - pick order = load priority (empty = all)
  const [partSel, setPartSel] = useState([]);
  const [startDate] = useState("");                    // empty = next working day
  const [timeSource, setTimeSource] = useState("actual");
  const [labelMode, setLabelMode] = useState("po");

  /* schedule result */
  const [data, setData] = useState(null);
  const [appliedQuery, setAppliedQuery] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [showWarn, setShowWarn] = useState(false);
  const [showAssume, setShowAssume] = useState(false);
  const reqRef = useRef(0);

  /* saved plans + planned vs actual */
  const [plans, setPlans] = useState([]);
  const [planId, setPlanId] = useState("");
  const [cmp, setCmp] = useState(null);
  const [cmpLoading, setCmpLoading] = useState(false);
  const [cmpError, setCmpError] = useState("");
  const [statusSel, setStatusSel] = useState([]);
  const [live, setLive] = useState(true);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [toast, setToast] = useState(null);
  const cmpReq = useRef(0);

  /* view / filters (client side, shared by the tabs) */
  const [view, setView] = useState("weekly");
  const [anchor, setAnchor] = useState(() => Date.now());
  const [customStart, setCustomStart] = useState(null);
  const [customEnd, setCustomEnd] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [stationSel, setStationSel] = useState([]);
  const [machineSel, setMachineSel] = useState([]);
  const [poFilter, setPoFilter] = useState([]);       // PO labels
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [hover, setHover] = useState(null);
  const [infoAnchor, setInfoAnchor] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [gridEl, setGridEl] = useState(null);
  const [gridW, setGridW] = useState(0);
  const fsRef = useRef(null);

  const authHeaders = () => ({ "x-access-token": localStorage.getItem("token") || "" });   // read at request time
  const planPos = useMemo(
    () => (poSel.length ? poSel : partSel.length ? orders.filter((o) => partSel.includes(o.part_number)) : []),
    [poSel, partSel, orders],
  );
  const query = buildQuery({ pos: planPos.map((o) => o.production_order), startDate, timeSource, labelMode, plant });

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

  /* ---- loaders ---- */
  const loadPlants = async () => {
    try {
      const res = await axios.get(`${apiBase}/schedule/po-gantt/plants`, { headers: authHeaders() });
      const list = res.data?.plants || [];
      setPlants(list);
      setPlant((cur) => cur || list[0]?.plant_code || "");
    } catch (err) {
      console.error(err);            // no plant list -> schedule without a plant filter
    } finally {
      setPlantsReady(true);
    }
  };

  const loadOrders = async (p = plant) => {
    try {
      const res = await axios.get(`${apiBase}/schedule/po-gantt/orders`, { headers: authHeaders(), params: p ? { plant: p } : {} });
      setOrders(res.data?.orders || []);
    } catch (err) {
      console.error(err);            // the picker falls back to the POs of the last schedule
    }
  };

  const generate = async (qOverride) => {
    const q = typeof qOverride === "string" ? qOverride : query;
    const id = ++reqRef.current;                      // only the latest request may update the page
    setLoading(true);
    setError("");
    try {
      const res = await axios.get(`${apiBase}/schedule/po-gantt?${q}`, { headers: authHeaders() });
      if (id !== reqRef.current) return;
      const d = prepareSchedule(res.data);
      if (!d?.stations?.length) {
        setData(null);
        setError("No yet-to-start production orders could be scheduled.");
        return;
      }
      setData(d);
      setAppliedQuery(q);
      if (tab !== 2) setAnchor(fromDateInput(d.meta?.start_date || d.days?.[0]?.date) || Date.now());
      setCustomStart(null);
      setCustomEnd(null);
      setPoFilter([]);
      setHover(null);
    } catch (err) {
      if (id !== reqRef.current) return;
      console.error(err);
      setData(null);
      setError(await errorText(err, "Failed to generate the schedule."));
    } finally {
      if (id === reqRef.current) setLoading(false);
    }
  };

  const loadPlans = async (p = plant, select) => {
    try {
      const res = await axios.get(`${apiBase}/schedule/plans`, { headers: authHeaders(), params: p ? { plant: p } : {} });
      const list = res.data?.plans || [];
      setPlans(list);
      setPlanId((cur) => {
        if (select) return select;
        if (cur && list.some((x) => x.id === cur)) return cur;
        return (list.find((x) => x.is_baseline) || list[0])?.id || "";
      });
    } catch (err) {
      console.error(err);
      setPlans([]);
    }
  };

  const loadCompare = async (id = planId, quiet = false) => {
    if (!id) { setCmp(null); return; }
    const rid = ++cmpReq.current;
    if (!quiet) setCmpLoading(true);
    setCmpError("");
    try {
      const res = await axios.get(`${apiBase}/schedule/plans/${id}/compare`, { headers: authHeaders() });
      if (rid !== cmpReq.current) return;
      const d = prepareCompare(res.data);
      setCmp(d);
      if (!quiet) {
        const start = fromDateInput(d.meta?.start_date) || Date.now();
        setAnchor(d._now && d._now > start ? d._now : start);
        setCustomStart(null);
        setCustomEnd(null);
      }
    } catch (err) {
      if (rid !== cmpReq.current) return;
      setCmp(null);
      setCmpError(await errorText(err, "Could not load planned vs actual."));
    } finally {
      if (rid === cmpReq.current) setCmpLoading(false);
    }
  };

  useEffect(() => { loadPlants(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  // plant change: reset the pickers, reload POs and saved plans
  useEffect(() => {
    if (!plantsReady) return;
    setPoSel([]);
    setPartSel([]);
    setOrders([]);
    loadOrders(plant);
    loadPlans(plant);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plantsReady, plant]);

  // ANY dropdown change -> rebuild the schedule (short debounce so multi-select clicks become one request)
  useEffect(() => {
    if (!plantsReady) return undefined;
    const t = setTimeout(() => generate(query), AUTO_GENERATE_DELAY);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plantsReady, query]);

  // Planned vs Actual: load when the plan changes / the tab opens; live refresh
  useEffect(() => {
    if (tab === 2) loadCompare(planId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, planId]);
  useEffect(() => {
    if (tab !== 2 || !live || !planId) return undefined;
    const t = setInterval(() => loadCompare(planId, true), LIVE_REFRESH_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, live, planId]);

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

  const savePlan = async ({ name, remarks, set_baseline: baseline }) => {
    setSaving(true);
    setSaveError("");
    try {
      const params = new URLSearchParams(appliedQuery || query);
      const body = {
        name, remarks, set_baseline: baseline, created_by: currentUser(),
        plant: params.get("plant") || null, production_order: params.getAll("production_order").length ? params.getAll("production_order") : null,
        start_date: params.get("start_date") || null, time_source: params.get("time_source") || timeSource,
        label_mode: params.get("label_mode") || labelMode,
      };
      const res = await axios.post(`${apiBase}/schedule/plans`, body, { headers: authHeaders() });
      const saved = res.data?.plan;
      setSaveOpen(false);
      await loadPlans(plant, baseline ? saved?.id : undefined);
      setToast({ text: `Plan "${saved?.name}" saved (${res.data?.items ?? 0} process runs)${baseline ? " as baseline" : ""}.`, planId: saved?.id });
    } catch (err) {
      setSaveError(await errorText(err, "Could not save the plan."));
    } finally {
      setSaving(false);
    }
  };

  // Reorder tab: the new order becomes the PO pick list (pick order = load priority) -> the schedule rebuilds itself
  const applyOrder = (newOrder) => {
    const known = Object.fromEntries([...orders, ...posMeta.map((p) => ({ production_order: p.production_order, part_number: p.part_number, quantity: p.quantity, role: p.role }))]
      .map((o) => [o.production_order, o]));
    setPoSel(newOrder.map((po) => known[po] || { production_order: po, part_number: "", quantity: 0, role: "MAIN" }));
    setToast({ text: "New PO order applied - the schedule is being rebuilt. Use Save Plan to keep it." });
  };

  const makeBaseline = async () => {
    if (!planId) return;
    try {
      await axios.put(`${apiBase}/schedule/plans/${planId}/baseline`, {}, { headers: authHeaders() });
      await loadPlans(plant, planId);
      setToast({ text: "Baseline updated." });
    } catch (err) {
      setCmpError(await errorText(err, "Could not set the baseline."));
    }
  };
  const deletePlan = async () => {
    const p = plans.find((x) => x.id === planId);
    if (!p || !window.confirm(`Delete saved plan "${p.name}"?`)) return;
    try {
      await axios.delete(`${apiBase}/schedule/plans/${planId}`, { headers: authHeaders() });
      setPlanId("");
      setCmp(null);
      await loadPlans(plant);
      setToast({ text: "Plan deleted." });
    } catch (err) {
      setCmpError(await errorText(err, "Could not delete the plan."));
    }
  };

  /* ---- view controls ---- */
  const scheduleStart = () => {
    const iso = tab === 2 ? cmp?.meta?.start_date : (data?.meta?.start_date || data?.days?.[0]?.date);
    return fromDateInput(iso) || Date.now();
  };
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
    if (tab !== 2) { setPoSel([]); setPartSel([]); }
    setStationSel([]);
    setMachineSel([]);
    setStatusSel([]);
    setPoFilter([]);
    setCustomStart(null);
    setCustomEnd(null);
    setZoom(1);
    setAnchor(scheduleStart());
  };
  const toggleGroup = useCallback((key) => setCollapsed((prev) => {
    const n = new Set(prev);
    if (n.has(key)) n.delete(key); else n.add(key);
    return n;
  }), []);
  const togglePoFilter = (label) => setPoFilter((prev) => (prev.includes(label) ? prev.filter((x) => x !== label) : [...prev, label]));

  /* ---- derived: schedule ---- */
  const meta = data?.meta;
  const warnings = data?.warnings || [];
  const assumptions = data?.assumptions || [];
  const posMeta = useMemo(() => meta?.pos || [], [meta]);
  const allRows = useMemo(() => data?.stations || [], [data]);
  const machineRows = useMemo(() => data?.machines || [], [data]);
  const colorMap = useMemo(() => buildColorMap(posMeta), [posMeta]);
  const dayWindow = useMemo(() => ({ start: meta?.day_window?.start_hour ?? 8, end: meta?.day_window?.end_hour ?? 22 }), [meta]);

  const orderOptions = useMemo(() => (orders.length ? orders : posMeta.map((p) => ({
    production_order: p.production_order, part_number: p.part_number, quantity: p.quantity, role: p.role,
  }))), [orders, posMeta]);
  const partRole = useMemo(() => Object.fromEntries(orderOptions.map((o) => [o.part_number, o.role])), [orderOptions]);
  const partOptions = useMemo(() => {
    const parts = Array.from(new Set(orderOptions.map((o) => o.part_number)));
    return parts.sort((a, b) => (partRole[a] === partRole[b] ? a.localeCompare(b) : partRole[a] === "CHILD" ? -1 : 1));
  }, [orderOptions, partRole]);
  const poPickOptions = useMemo(
    () => (partSel.length ? orderOptions.filter((o) => partSel.includes(o.part_number)) : orderOptions),
    [orderOptions, partSel],
  );
  const onPartChange = (v) => {
    setPartSel(v);
    setPoSel((prev) => (v.length ? prev.filter((o) => v.includes(o.part_number)) : prev));
  };
  const stationOptions = useMemo(() => Array.from(new Set(allRows.map((r) => r.name))), [allRows]);
  const machineOptions = useMemo(() => machineRows.map((m) => m.machine_id), [machineRows]);
  const machineName = useMemo(() => Object.fromEntries(machineRows.map((m) => [m.machine_id, m.name])), [machineRows]);

  const activeLabels = useMemo(() => (poFilter.length ? new Set(poFilter) : null), [poFilter]);

  /* ---- tab 1: PO on Process ---- */
  const processGroups = useMemo(() => {
    const routeRows = activeLabels ? new Set(posMeta.filter((p) => activeLabels.has(p.label)).flatMap((p) => p.route || [])) : null;
    const rows = allRows.filter((r) => (!routeRows || routeRows.has(r.row_id)) && (!stationSel.length || stationSel.includes(r.name)));
    return ["CHILD", "MAIN"].map((role) => {
      const rs = rows.filter((r) => r.section === role).map((r) => {
        const n = (r.real_machines || []).length;
        const processText = r.kind === "LINE" ? `${r.name} (${(r.steps || []).length} steps)` : r.name;
        return {
          id: r.row_id, height: ROW_H.process, title: r.name,
          subtitle: `${(r.part_numbers || []).join(", ")}${(r.shared_with || []).length ? ` · shared with ${r.shared_with.map((x) => SECTIONS[x]?.tag || x).join(", ")}` : ""}`,
          badge: r.has_machine
            ? { icon: <BuildIcon sx={{ fontSize: 13 }} />, text: String(n), color: THEME.machine, bg: "#fff1d6", border: THEME.machineBorder, tip: <><b>{n} machine{n === 1 ? "" : "s"}</b>{(r.real_machine_names || []).map((m, i) => <div key={i}>{m} ({r.real_machines[i]})</div>)}</> }
            : { text: "Manual", color: THEME.manual, bg: THEME.manualBg },
          badge2: r.kind === "LINE" ? { text: "LINE", color: "#7048e8", bg: "#f3f0ff", tip: <><b>Run in one go within one day:</b>{(r.steps || []).map((s, i) => <div key={s}>{i + 1}. {s}</div>)}</> } : null,
          right: [`${r.shifts} shift`, `${(r.downtime || []).length ? `${(r.downtime || []).length} down` : r.has_machine ? "" : "no m/c"}`].filter(Boolean),
          accent: r.has_machine ? THEME.machineBorder : "#d1d5db", tint: r.has_machine ? THEME.machineBg : "#fff",
          lanes: Math.min(3, Math.max(1, new Set((r.segments || []).map((s) => s.machine_no)).size)),
          children: r.kind === "LINE" ? r.steps : null,
          bars: (r.segments || []).map((s) => {
            const lanesOf = Array.from(new Set((r.segments || []).map((x) => x.machine_no))).sort((a, b) => a - b);
            return {
              s: s._s, e: s._e, lane: Math.max(0, lanesOf.indexOf(s.machine_no)) % 3, color: colorMap[s.label], label: s.label,
              sub: `${hm(s._s)} – ${hm(s._e)}`, dimKey: s.label,
              card: segCard(s, colorMap[s.label], processText, [r.has_machine ? ["Machine", (s.machines || []).length > 1 ? s.machines.join(", ") : `${machineName[s.machine] || s.machine} (${s.machine})`] : ["Machine", "Manual"]]),
            };
          }),
          downs: (r.downtime || []).map((e) => ({ s: e._s, e: e._e, card: downCard(e) })), downMode: "strip",
        };
      });
      return { key: role, title: SECTIONS[role].title, color: SECTIONS[role].color, bg: SECTIONS[role].bg, rows: rs, countText: `${rs.length} process${rs.length === 1 ? "" : "es"}` };
    });
  }, [allRows, posMeta, activeLabels, stationSel, colorMap, machineName]);

  /* ---- tab 2: PO on Machines ---- */
  const machineGroups = useMemo(() => {
    const out = [];
    const byKey = {};
    machineRows.forEach((m) => {
      if (machineSel.length && !machineSel.includes(m.machine_id)) return;
      if (stationSel.length && !(m.processes || []).some((p) => stationSel.includes(p))) return;
      if (activeLabels && !(m.segments || []).some((s) => activeLabels.has(s.label))) return;
      if (!byKey[m.group]) {
        byKey[m.group] = { key: `M-${m.group}`, title: m.group_name, color: THEME.machine, bg: "#fff6e5", rows: [], upper: true,
          tag: m.group_kind === "LINE" ? <Box component="span" sx={{ fontSize: 11, fontWeight: 700, color: "#7048e8", bgcolor: "#f3f0ff", px: 0.6, borderRadius: "4px", textTransform: "none" }}>LINE</Box> : null };
        out.push(byKey[m.group]);
      }
      const busy = m.busy_minutes || 0;
      byKey[m.group].rows.push({
        id: m.row_id, height: ROW_H.machine, title: m.name,
        subtitle: [m.machine_id, m.step, [m.make, m.model].filter(Boolean).join(" "), (m.processes || []).length > 1 ? `also: ${m.processes.slice(1).join(", ")}` : null].filter(Boolean).join(" · "),
        badge: (m.downtime || []).length ? { text: `${m.downtime.length} down`, color: THEME.down, bg: "#fff0f0", tip: m.downtime.map((e, i) => <div key={i}>{e.kind === "PM" ? "PM" : "Breakdown"}: {fmtDateTime(e._s)} → {fmtDateTime(e._e)}</div>) } : null,
        right: [`${(busy / 60).toFixed(1)} h load`, `${new Set((m.segments || []).map((s) => s.po)).size} PO`],
        accent: THEME.machineBorder, tint: "#fff",
        bars: (m.segments || []).map((s) => ({
          s: s._s, e: s._e, color: colorMap[s.label], label: s.label, sub: `${hm(s._s)} – ${hm(s._e)}`, dimKey: s.label,
          card: segCard(s, colorMap[s.label], s.operation === s.step || !s.step ? s.operation : `${s.operation} · ${s.step}`, [["Machine", `${m.name} (${m.machine_id})`]]),
        })),
        downs: (m.downtime || []).map((e) => ({ s: e._s, e: e._e, card: downCard({ ...e, machine_name: m.name }) })), downMode: "full",
      });
    });
    out.forEach((g) => { g.countText = `${g.rows.length} machine${g.rows.length === 1 ? "" : "s"}`; });
    return out;
  }, [machineRows, machineSel, stationSel, activeLabels, colorMap]);

  /* ---- tab 3: Planned vs Actual ---- */
  const cmpPos = useMemo(() => cmp?.pos || [], [cmp]);
  const cmpColor = useMemo(() => buildColorMap(cmp?.meta?.pos || []), [cmp]);
  const cmpStationOptions = useMemo(() => Array.from(new Set((cmp?.rows || []).map((r) => r.name))), [cmp]);
  const cmpActive = useMemo(() => {
    if (!statusSel.length && !poFilter.length) return null;
    return new Set(cmpPos.filter((p) => (!statusSel.length || statusSel.includes(p.status)) && (!poFilter.length || poFilter.includes(p.label))).map((p) => p.label));
  }, [cmpPos, statusSel, poFilter]);
  const compareGroups = useMemo(() => {
    const rows = (cmp?.rows || []).filter((r) => (!stationSel.length || stationSel.includes(r.name))
      && (!cmpActive || (r.items || []).some((i) => cmpActive.has(i.label))));
    return ["CHILD", "MAIN"].map((role) => {
      const rs = rows.filter((r) => r.section === role).map((r) => {
        const bars = [];
        (r.items || []).forEach((i) => {
          const c = cmpColor[i.label] || PO_PALETTE[0];
          const st = STATUS[i.status] || STATUS.UPCOMING;
          const card = {
            title: i.label === i.po ? `PO ${i.po}` : `${i.label} · PO ${i.po}`, color: c,
            tag: { text: st.label, color: st.color, bg: st.bg },
            lines: [
              ["Part number", i.part], ["Process", r.name], ["Planned", `${fmtIso(i.planned_start)} → ${fmtIso(i.planned_end)}`],
              ["Actual start", fmtIso(i.actual_start)], ["Actual finish", i.actual_end ? fmtIso(i.actual_end) : i.actual_start ? "running…" : "–"],
              ["Progress", `${i.done_qty} / ${i.total_qty} pcs${i.wip_qty ? ` (${i.wip_qty} in work)` : ""}`],
              ["Variance", fmtVariance(i.variance_min)],
              i.operators?.length ? ["Operators", i.operators.join(", ")] : null,
              ["Machine", (i.actual_machines || []).length ? `${i.actual_machines.join(", ")} (planned ${i.machine})` : i.machine],
            ],
          };
          bars.push({ s: i._ps, e: i._pe, lane: 0, color: c, label: i.label, sub: `${hm(i._ps)} – ${hm(i._pe)}`, dimKey: i.label,
            variant: i.status === "START_OVERDUE" ? "overdue" : "plan", card });
          if (i._as) {
            const running = !i.actual_end;
            bars.push({ s: i._as, e: Math.max(i._au || i._as, i._as + 60000), lane: 1, color: st.color, label: i.label,
              sub: running ? `${i.done_qty}/${i.total_qty} pcs` : `${hm(i._as)} – ${hm(i._au)}`, dimKey: i.label,
              variant: running ? "stripes" : "solid", card });
          }
        });
        const late = (r.items || []).filter((i) => ["DONE_LATE", "RUNNING_LATE", "START_OVERDUE"].includes(i.status)).length;
        return {
          id: r.row_id, height: ROW_H.compare, title: r.name, lanes: 2,
          subtitle: `${(r.items || []).length} PO run${(r.items || []).length === 1 ? "" : "s"}${late ? ` · ${late} behind` : ""}`,
          badge: r.has_machine ? { icon: <BuildIcon sx={{ fontSize: 13 }} />, text: "Machine", color: THEME.machine, bg: "#fff1d6", border: THEME.machineBorder } : { text: "Manual", color: THEME.manual, bg: THEME.manualBg },
          badge2: late ? { text: `${late} late`, color: STATUS.DONE_LATE.color, bg: STATUS.DONE_LATE.bg } : null,
          laneLabels: [{ text: "Plan", color: "#64748b" }, { text: "Actual", color: THEME.text }],
          accent: r.has_machine ? THEME.machineBorder : "#d1d5db", tint: r.has_machine ? THEME.machineBg : "#fff",
          bars,
        };
      });
      return { key: `C-${role}`, title: SECTIONS[role].title, color: SECTIONS[role].color, bg: SECTIONS[role].bg, rows: rs, countText: `${rs.length} process${rs.length === 1 ? "" : "es"}` };
    });
  }, [cmp, stationSel, cmpActive, cmpColor]);

  /* ---- shared numbers ---- */
  const counts = useMemo(() => ({
    child: posMeta.filter((p) => p.role === "CHILD").length,
    main: posMeta.filter((p) => p.role === "MAIN").length,
  }), [posMeta]);
  const rangeEndInclusive = addDays(range.end, -1);
  const activeGroups = tab === 0 ? processGroups : tab === 1 ? machineGroups : compareGroups;
  const visibleRowCount = activeGroups.reduce((n, g) => n + g.rows.length, 0);
  const hasWorkInRange = useMemo(
    () => activeGroups.some((g) => g.rows.some((r) => (r.bars || []).some((b) => b.e > range.start && b.s < range.end))),
    [activeGroups, range],
  );
  const periodText = `${fmtShortDate(range.start)}${range.end - range.start > DAY ? ` – ${fmtShortDate(rangeEndInclusive)}` : ""}`;
  const granText = view === "daily" || view === "weekly"
    ? (range.end - range.start > 14 * DAY ? "day-wise" : `hour-wise, ${pad(Math.floor(dayWindow.start))}:00 – ${pad(Math.min(24, Math.ceil(dayWindow.end)))}:00`)
    : view === "monthly" ? "day-wise" : "month-wise";
  const cmpDayWindow = useMemo(() => ({ start: cmp?.meta?.day_window?.start_hour ?? 8, end: cmp?.meta?.day_window?.end_hour ?? 22 }), [cmp]);
  const selectedPlan = plans.find((p) => p.id === planId);

  const fsEl = isFullscreen ? fsRef.current : null;
  const planSummary = data ? `${meta?.number_of_pos} POs · ${fmtLong(meta?.start_date)} → ${fmtLong(meta?.finish_date)} · plant ${plant || "all"} · ${timeSource === "sap" ? "SAP" : "MES"} time` : "";

  const titleByTab = ["PO on Process", "PO on Machines", "Planned vs Actual", "Reorder POs"];
  const showChart = tab === 2 ? !!cmp : tab === 3 ? false : !!data;

  return (
    <FsContext.Provider value={fsEl}>
      <Box ref={fsRef} sx={{ p: isFullscreen ? 2 : 2.5, bgcolor: isFullscreen ? "#eef1f6" : "transparent", overflow: "auto", height: isFullscreen ? "100vh" : "auto", boxSizing: "border-box" }}>
        <Box sx={{ bgcolor: "#fff", border: `1px solid ${THEME.border}`, borderRadius: "14px", p: { xs: 2, md: 3 } }}>
          {/* header */}
          <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" sx={{ gap: 1.5, mb: 1 }}>
            <Typography sx={{ fontSize: 22, fontWeight: 700, color: THEME.text }}>
              Production Schedule <Box component="span" sx={{ color: THEME.muted, fontWeight: 500 }}>– {titleByTab[tab]}</Box>
            </Typography>
            <Stack direction="row" flexWrap="wrap" sx={{ gap: 1.25 }}>
              {tab !== 2 && (
                <>
                  <Button variant="outlined" startIcon={<DownloadIcon />} onClick={exportXlsx} disabled={!data || exporting}
                    sx={{ ...btnSx, borderColor: THEME.primary, color: THEME.primary }}>
                    {exporting ? "Exporting…" : "Export Excel"}
                  </Button>
                  <Button variant="outlined" startIcon={<EditIcon />} onClick={() => setEditOpen(true)} disabled={!plant}
                    sx={{ ...btnSx, borderColor: THEME.primary, color: THEME.primary }}>
                    Edit Process Times
                  </Button>
                  <Button variant="contained" startIcon={<SaveIcon />} onClick={() => { setSaveError(""); setSaveOpen(true); }} disabled={!data || loading}
                    sx={{ ...btnSx, bgcolor: "#2f9e44", "&:hover": { bgcolor: "#2b8a3e", boxShadow: "none" } }}>
                    Save Plan
                  </Button>
                </>
              )}
              <Button variant="contained" startIcon={<RefreshIcon />} disabled={tab === 2 ? cmpLoading || !planId : loading}
                onClick={() => (tab === 2 ? loadCompare(planId) : generate())}
                sx={{ ...btnSx, bgcolor: THEME.primary, "&:hover": { bgcolor: THEME.primaryDark, boxShadow: "none" } }}>
                {tab === 2 ? (cmpLoading ? "Refreshing…" : "Refresh actuals") : loading ? "Scheduling…" : "Regenerate"}
              </Button>
              <Tooltip title={isFullscreen ? "Exit full screen" : "Full screen"}>
                <IconButton aria-label="Full screen" onClick={toggleFullscreen} sx={toolSx}>
                  {isFullscreen ? <FullscreenExitIcon /> : <FullscreenIcon />}
                </IconButton>
              </Tooltip>
            </Stack>
          </Stack>

          <Tabs value={tab} onChange={(_, v) => { setTab(v); setHover(null); setPoFilter([]); }}
            sx={{ mb: 2, minHeight: 48, borderBottom: `1px solid ${THEME.border}`, "& .MuiTab-root": { textTransform: "none", fontSize: 15.5, fontWeight: 600, minHeight: 48, px: 2.5 } }}>
            <Tab value={0} icon={<ProcessTabIcon fontSize="small" />} iconPosition="start" label="PO on Process" />
            <Tab value={1} icon={<MachineIcon fontSize="small" />} iconPosition="start" label="PO on Machines" />
            <Tab value={3} icon={<ReorderIcon fontSize="small" />} iconPosition="start" label="Reorder POs" />
            <Tab value={2} icon={<CompareIcon fontSize="small" />} iconPosition="start" label="Planned vs Actual" />
          </Tabs>

          {/* controls */}
          <Panel title={tab === 2 ? "Saved plan & filter" : "Plan & filter"}
            right={tab !== 2 && loading ? <Typography sx={{ fontSize: 13, color: THEME.primary, fontWeight: 600 }}>Updating schedule…</Typography> : null}>
            {tab !== 2 ? (
              <FieldRow cols="minmax(0,1.1fr) minmax(0,1.6fr) minmax(0,3.2fr) minmax(0,1fr)">
                <SelectField label="Plant" value={plant} onChange={setPlant}
                  options={(plants.length ? plants : [{ plant_code: "", location: "All plants" }]).map((p) => ({ value: p.plant_code, label: p.location ? `${p.plant_code} · ${p.location}` : p.plant_code || "All" }))} />
                <MultiSelect label="Part number" placeholder="All parts" options={partOptions} value={partSel} onChange={onPartChange}
                  renderOption={({ key, ...props }, pn) => (
                    <li key={key ?? pn} {...props}>
                      <Box sx={{ display: "flex", width: "100%", fontSize: 15 }}>
                        {pn}
                        <Box component="span" sx={{ ml: "auto", fontSize: 12, fontWeight: 700, color: SECTIONS[partRole[pn]]?.color }}>{SECTIONS[partRole[pn]]?.tag}</Box>
                      </Box>
                    </li>
                  )} />
                <MultiSelect
                  label="Production orders (pick order = priority)" placeholder="All yet-to-start POs" limitTags={3}
                  options={poPickOptions} value={poSel} onChange={setPoSel}
                  getLabel={(o) => `${o.production_order} · ${o.part_number}`}
                  renderOption={({ key, ...props }, o) => (
                    <li key={key ?? o.production_order} {...props}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%", fontSize: 15 }}>
                        <b>{o.production_order}</b>
                        <Box component="span" sx={{ color: THEME.muted }}>{o.part_number} · {o.quantity} pcs</Box>
                        <Box component="span" sx={{ ml: "auto", fontSize: 12, fontWeight: 700, color: SECTIONS[o.role]?.color, bgcolor: SECTIONS[o.role]?.bg, px: 0.75, borderRadius: "4px" }}>
                          {SECTIONS[o.role]?.tag || o.role}
                        </Box>
                      </Box>
                    </li>
                  )}
                />
                <SelectField label="Time basis" value={timeSource} onChange={setTimeSource} options={TIME_SOURCES} />
              </FieldRow>
            ) : (
              <FieldRow cols="minmax(0,1.1fr) minmax(0,3fr) minmax(0,2fr) auto">
                <SelectField label="Plant" value={plant} onChange={setPlant}
                  options={(plants.length ? plants : [{ plant_code: "", location: "All plants" }]).map((p) => ({ value: p.plant_code, label: p.location ? `${p.plant_code} · ${p.location}` : p.plant_code || "All" }))} />
                <SelectField label="Saved plan" value={plans.some((p) => p.id === planId) ? planId : ""} onChange={setPlanId}
                  options={plans.length ? plans.map((p) => ({
                    value: p.id, label: p.name,
                    node: (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
                        {p.is_baseline ? <StarIcon sx={{ color: "#f59f00", fontSize: 19 }} /> : <StarBorderIcon sx={{ color: "#ced4da", fontSize: 19 }} />}
                        <b>{p.name}</b>
                        <Box component="span" sx={{ ml: "auto", color: THEME.muted, fontSize: 13 }}>{p.number_of_pos} POs · {fmtLong(p.start_date)} → {fmtLong(p.finish_date)} · saved {fmtIso(p.created_at)}</Box>
                      </Box>
                    ),
                  })) : [{ value: "", label: "No saved plan yet - use “Save Plan” on the first tab" }]}
                  renderValue={(v) => {
                    const p = plans.find((x) => x.id === v);
                    return p ? `${p.is_baseline ? "★ " : ""}${p.name}  ·  ${p.number_of_pos} POs · ${fmtLong(p.start_date)} → ${fmtLong(p.finish_date)}` : "No saved plan yet";
                  }} />
                <MultiSelect label="Status" placeholder="All statuses" options={STATUS_ORDER} value={statusSel} onChange={setStatusSel}
                  getLabel={(s) => STATUS[s]?.label || s}
                  renderOption={({ key, ...props }, s) => <li key={key ?? s} {...props}><StatusChip status={s} /></li>} />
                <Stack direction="row" alignItems="center" sx={{ gap: 0.5 }}>
                  <Tooltip title={selectedPlan?.is_baseline ? "This plan is the baseline" : "Make this plan the baseline"}>
                    <span><IconButton onClick={makeBaseline} disabled={!planId || selectedPlan?.is_baseline} sx={{ ...toolSx, color: "#f59f00" }}>{selectedPlan?.is_baseline ? <StarIcon /> : <StarBorderIcon />}</IconButton></span>
                  </Tooltip>
                  <Tooltip title="Delete this saved plan">
                    <span><IconButton onClick={deletePlan} disabled={!planId} sx={{ ...toolSx, color: THEME.down }}><DeleteIcon /></IconButton></span>
                  </Tooltip>
                  <FormControlLabel sx={{ ml: 0.5, mr: 0 }} control={<Switch checked={live} onChange={(e) => setLive(e.target.checked)} />}
                    label={<Box sx={{ fontSize: 14.5, fontWeight: 600 }}>Live</Box>} />
                </Stack>
              </FieldRow>
            )}

            {tab !== 3 && <FieldRow divider cols={tab === 2 ? "minmax(0,0.9fr) minmax(0,1.8fr) minmax(0,2.6fr) auto auto" : "minmax(0,0.9fr) minmax(0,1.8fr) minmax(0,2.6fr) minmax(0,1.1fr) auto auto"}>
              <SelectField label="View" value={view} onChange={changeView} options={VIEW_MODES} />
              <DateRangeField start={customStart || range.start} end={customEnd || rangeEndInclusive}
                onChange={(s, e) => { setCustomStart(s); setCustomEnd(e); }} />
              {tab === 1 ? (
                <MultiSelect label="Machines" placeholder="All machines" options={machineOptions} value={machineSel} onChange={setMachineSel}
                  getLabel={(m) => `${machineName[m] || m} (${m})`} />
              ) : (
                <MultiSelect label="Process" placeholder="All processes" options={tab === 2 ? cmpStationOptions : stationOptions} value={stationSel} onChange={setStationSel} />
              )}
              {tab !== 2 && <SelectField label="Bar labels" value={labelMode} onChange={setLabelMode} options={LABEL_MODES} />}
              <ChartTools zoomIn={zoomIn} zoomOut={zoomOut} onInfo={(e) => setInfoAnchor(e.currentTarget)} />
              <Button variant="contained" startIcon={<ClearIcon />} onClick={clearFilters}
                sx={{ ...btnSx, bgcolor: THEME.dark, "&:hover": { bgcolor: "#4a5361", boxShadow: "none" } }}>
                Clear Filters
              </Button>
            </FieldRow>}
          </Panel>

          <InfoPopover anchorEl={infoAnchor} onClose={() => setInfoAnchor(null)} lineGroups={(tab === 2 ? cmp?.meta : meta)?.line_groups}
            tab={["process", "machine", "compare", "reorder"][tab]} />
          <ProcessTimeDialog open={editOpen} onClose={() => setEditOpen(false)} apiBase={apiBase} plant={plant}
            authHeaders={authHeaders} timeSource={timeSource} onSaved={() => { setEditOpen(false); generate(); }} />
          <SavePlanDialog open={saveOpen} onClose={() => setSaveOpen(false)} onSave={savePlan} saving={saving} error={saveError} summary={planSummary} />

          {(tab === 2 ? cmpLoading : loading) && <LinearProgress sx={{ mb: 1.5, borderRadius: 1 }} />}
          {tab !== 2 && error && <Alert severity="warning" sx={{ mb: 2, fontSize: 14.5 }}><b>Notice:</b> {error}</Alert>}
          {tab === 2 && cmpError && <Alert severity="warning" sx={{ mb: 2, fontSize: 14.5 }}>{cmpError}</Alert>}

          {/* summary */}
          {tab !== 2 && data && (
            <>
              <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 1.25, mb: 1.5, fontSize: 14.5, color: "#374151" }}>
                <Chip label={<span><b>{meta?.number_of_pos ?? posMeta.length}</b> POs</span>} sx={{ fontSize: 14 }} />
                <Chip sx={{ fontSize: 14, bgcolor: SECTIONS.CHILD.bg, color: SECTIONS.CHILD.color }} label={<span><b>{counts.child}</b> child</span>} />
                <Chip sx={{ fontSize: 14, bgcolor: SECTIONS.MAIN.bg, color: SECTIONS.MAIN.color }} label={<span><b>{counts.main}</b> main</span>} />
                {meta?.machines_down > 0 && (
                  <Chip icon={<BuildIcon sx={{ fontSize: 16, color: `${THEME.down} !important` }} />} sx={{ fontSize: 14, bgcolor: "#fff0f0", color: THEME.down, fontWeight: 600 }}
                    label={`${meta.machines_down} machine${meta.machines_down === 1 ? "" : "s"} down / in maintenance`} onClick={() => setTab(1)} />
                )}
                <Box sx={{ mx: 0.5 }}>
                  {fmtLong(meta?.start_date)} → <b>{fmtLong(meta?.finish_date)}</b> · <b>{meta?.working_days}</b> working day(s)
                </Box>
                <Box sx={{ ml: "auto", display: "flex", gap: 1 }}>
                  {warnings.length > 0 && (
                    <Button color="warning" startIcon={<WarnIcon />} onClick={() => setShowWarn(!showWarn)} sx={{ textTransform: "none", fontWeight: 600, fontSize: 14.5 }}>
                      {warnings.length} warning{warnings.length === 1 ? "" : "s"}
                    </Button>
                  )}
                  {assumptions.length > 0 && (
                    <Button onClick={() => setShowAssume(!showAssume)} sx={{ textTransform: "none", fontSize: 14.5, whiteSpace: "nowrap" }}>
                      {showAssume ? "Hide" : "Show"} assumptions
                    </Button>
                  )}
                </Box>
              </Stack>
              <Collapse in={showWarn && warnings.length > 0}>
                <Alert severity="warning" sx={{ mb: 1.5, fontSize: 14 }} onClose={() => setShowWarn(false)}>
                  <Box component="ul" sx={{ m: 0, pl: 2.25, maxHeight: 200, overflow: "auto" }}>
                    {warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </Box>
                </Alert>
              </Collapse>
              <Collapse in={showAssume}>
                <Box component="ul" sx={{ m: 0, mb: 1.5, pl: 2.5, fontSize: 13.5, color: "#4b5563", bgcolor: THEME.panelBg, borderRadius: "8px", py: 1, pr: 1.5 }}>
                  {assumptions.map((a, i) => <li key={i}>{a}</li>)}
                </Box>
              </Collapse>
            </>
          )}

          {tab === 2 && cmp && (
            <Box sx={{ display: "grid", gap: 1.5, mb: 2, gridTemplateColumns: { xs: "repeat(2, minmax(0,1fr))", md: "repeat(4, minmax(0,1fr))", xl: "repeat(7, minmax(0,1fr))" } }}>
              <KpiCard label="POs in plan" value={cmp.kpis?.total_pos ?? 0} color={THEME.text} onClick={() => setStatusSel([])} active={!statusSel.length} />
              {STATUS_ORDER.map((s) => (
                <KpiCard key={s} label={STATUS[s].label} value={cmp.kpis?.pos?.[s] || 0} color={STATUS[s].color} bg={STATUS[s].bg}
                  active={statusSel.includes(s)} onClick={() => setStatusSel((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))} />
              ))}
            </Box>
          )}
          {tab === 2 && !cmp && !cmpLoading && !cmpError && (
            <Box sx={{ textAlign: "center", p: 6, color: "#4b5563", bgcolor: "#f8f9fa", borderRadius: "10px", fontSize: 15 }}>
              {plans.length ? "Pick a saved plan to compare it with what is happening on the floor." : <>No saved plan for this plant yet. Generate a schedule on <b>PO on Process</b> and press <b>Save Plan</b>.</>}
            </Box>
          )}

          {tab === 3 && data && (
            <ReorderPanel data={data} apiBase={apiBase} authHeaders={authHeaders} plant={plant} startDate={startDate}
              timeSource={timeSource} labelMode={labelMode} colorMap={colorMap} onApply={applyOrder} />
          )}

          {/* chart */}
          {showChart ? (
            <>
              <Box sx={{ border: `1px solid ${THEME.border}`, borderRadius: "12px", overflow: "hidden", bgcolor: "#fff" }}>
                <Stack direction="row" alignItems="center" sx={{ px: 1, py: 0.75, gap: 0.75, borderBottom: `1px solid ${THEME.border}`, bgcolor: "#fff" }}>
                  <Tooltip title="Previous period"><IconButton aria-label="Previous" onClick={() => navigate(-1)} sx={{ ...toolSx, border: `1px solid ${THEME.border}` }}><PrevIcon /></IconButton></Tooltip>
                  <Box sx={{ flex: 1, textAlign: "center", fontSize: 15, fontWeight: 600, color: THEME.text }}>
                    {periodText} <Box component="span" sx={{ fontWeight: 400, color: THEME.muted }}>· {granText}</Box>
                    {(activeLabels || (tab === 2 && cmpActive)) && <Box component="span" sx={{ fontWeight: 500, color: THEME.primary }}> · showing {visibleRowCount} row(s) of the selected PO(s)</Box>}
                    {tab === 2 && cmp?.now && <Box component="span" sx={{ fontWeight: 400, color: THEME.muted }}> · actuals as of {fmtIso(cmp.now)}</Box>}
                  </Box>
                  <Button onClick={() => goTo(Date.now())} sx={{ textTransform: "none", minWidth: 0, fontSize: 14.5 }}>Today</Button>
                  <Button onClick={() => goTo(scheduleStart())} sx={{ textTransform: "none", minWidth: 0, fontSize: 14.5 }}>{tab === 2 ? "Plan start" : "Schedule start"}</Button>
                  <Tooltip title="Next period"><IconButton aria-label="Next" onClick={() => navigate(1)} sx={{ ...toolSx, border: `1px solid ${THEME.border}` }}><NextIcon /></IconButton></Tooltip>
                </Stack>

                {!hasWorkInRange && visibleRowCount > 0 && (
                  <Alert severity="info" sx={{ borderRadius: 0, fontSize: 14 }}
                    action={<Button color="inherit" onClick={() => goTo(scheduleStart())}>Go to {tab === 2 ? "plan" : "schedule"} start</Button>}>
                    Nothing scheduled in this period.
                  </Alert>
                )}

                {visibleRowCount ? (
                  <Box ref={setGridEl} onScroll={() => hover && setHover(null)}
                    sx={{ overflow: "auto", maxHeight: isFullscreen ? "calc(100vh - 360px)" : "calc(100vh - 300px)", minHeight: 320 }}>
                    <GanttGrid
                      groups={activeGroups} days={tab === 2 ? cmp?.days : data?.days} dayWindow={tab === 2 ? cmpDayWindow : dayWindow}
                      view={view} range={range} zoom={zoom} availableWidth={Math.max(0, gridW - LAYOUT.labelWidth - 2)}
                      activeLabels={tab === 2 ? cmpActive : activeLabels} collapsed={collapsed} onToggleGroup={toggleGroup} onHover={setHover}
                      labelTitle={["Process", "Machine", "Process"][tab]} labelRight={["shifts · machines", "load · POs", "lane"][tab]}
                      nowTs={tab === 2 ? cmp?._now : undefined}
                    />
                  </Box>
                ) : (
                  <Box sx={{ p: 5, textAlign: "center", color: THEME.muted, fontSize: 15 }}>
                    {tab === 1 && !machineRows.length ? "No machines are mapped to the processes of this schedule (equipment_details)." : "Nothing matches the filters."}
                    {" "}<Button onClick={clearFilters}>Clear filters</Button>
                  </Box>
                )}
              </Box>

              {tab === 1 && (meta?.manual_processes || []).length > 0 && (
                <Typography sx={{ mt: 1, fontSize: 13.5, color: THEME.muted }}>
                  Manual processes (no machine, shown on <b>PO on Process</b>): {meta.manual_processes.filter((v, i, a) => a.indexOf(v) === i).join(", ")}
                </Typography>
              )}

              {tab !== 2 ? (
                <ProductionOrdersLegend pos={posMeta} colorMap={colorMap} selected={poFilter} onToggle={togglePoFilter} onSelectSet={setPoFilter}
                  extra={
                    <Stack direction="row" flexWrap="wrap" sx={{ gap: 2 }}>
                      {tab === 0 && <LegendSwatch sx={{ bgcolor: THEME.machineBg, border: `2px solid ${THEME.machineBorder}` }}>Process with machine</LegendSwatch>}
                      {tab === 0 && <LegendSwatch sx={{ bgcolor: "#fff", border: "2px solid #d1d5db" }}>Manual process</LegendSwatch>}
                      <LegendSwatch sx={{ background: HATCH(THEME.down), border: `1px solid ${alpha(THEME.down, 0.45)}` }}>Breakdown / maintenance</LegendSwatch>
                    </Stack>
                  } />
              ) : (
                <>
                  <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 2.5, mt: 1.5 }}>
                    <LegendSwatch sx={{ bgcolor: alpha(PO_PALETTE[0], 0.22), border: `1.5px solid ${PO_PALETTE[0]}` }}>Plan (PO colour)</LegendSwatch>
                    <LegendSwatch sx={{ bgcolor: alpha(PO_PALETTE[0], 0.16), border: `2px dashed ${STATUS.START_OVERDUE.color}` }}>Planned start passed, not started</LegendSwatch>
                    <LegendSwatch sx={{ bgcolor: STATUS.DONE_ON_TIME.color }}>Done on time</LegendSwatch>
                    <LegendSwatch sx={{ bgcolor: STATUS.DONE_LATE.color }}>Done late</LegendSwatch>
                    <LegendSwatch sx={{ background: STRIPES(STATUS.RUNNING.color) }}>In progress</LegendSwatch>
                    <LegendSwatch sx={{ background: STRIPES(STATUS.RUNNING_LATE.color) }}>Running late</LegendSwatch>
                  </Stack>

                  {/* PO table */}
                  <Typography sx={{ fontSize: 16, fontWeight: 700, mt: 2.5, mb: 1 }}>Production orders <Box component="span" sx={{ fontWeight: 400, fontSize: 14, color: THEME.muted }}>(click a row to focus the chart on it)</Box></Typography>
                  <TableContainer sx={{ maxHeight: 420, border: `1px solid ${THEME.border}`, borderRadius: "10px" }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          {["PO", "Part", "Type", "Planned start", "Planned finish", "Actual start", "Actual finish", "Progress", "Current process", "Status", "Variance"].map((h) => (
                            <TableCell key={h} sx={{ fontWeight: 700, fontSize: 13.5, bgcolor: THEME.headBg, whiteSpace: "nowrap" }}>{h}</TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {cmpPos.filter((p) => !cmpActive || cmpActive.has(p.label) || poFilter.includes(p.label)).map((p) => {
                          const on = poFilter.includes(p.label);
                          const pct = p.processes ? Math.round((100 * p.processes_done) / p.processes) : 0;
                          return (
                            <TableRow key={p.po} hover selected={on} onClick={() => togglePoFilter(p.label)} sx={{ cursor: "pointer", "& td": { fontSize: 14 } }}>
                              <TableCell sx={{ whiteSpace: "nowrap" }}>
                                <Stack direction="row" alignItems="center" sx={{ gap: 0.75 }}>
                                  <Box sx={{ width: 12, height: 12, borderRadius: "3px", bgcolor: cmpColor[p.label] }} />
                                  <b>{p.po}</b>{p.label !== p.po && <Box component="span" sx={{ color: THEME.muted }}>({p.label})</Box>}
                                </Stack>
                              </TableCell>
                              <TableCell>{p.part}</TableCell>
                              <TableCell><Box component="span" sx={{ fontWeight: 700, color: SECTIONS[p.role]?.color }}>{SECTIONS[p.role]?.tag}</Box></TableCell>
                              <TableCell sx={{ whiteSpace: "nowrap" }}>{fmtIso(p.planned_start)}</TableCell>
                              <TableCell sx={{ whiteSpace: "nowrap" }}>{fmtIso(p.planned_end)}</TableCell>
                              <TableCell sx={{ whiteSpace: "nowrap" }}>{fmtIso(p.actual_start)}</TableCell>
                              <TableCell sx={{ whiteSpace: "nowrap" }}>{fmtIso(p.actual_end)}</TableCell>
                              <TableCell sx={{ minWidth: 130 }}>
                                <Stack direction="row" alignItems="center" sx={{ gap: 1 }}>
                                  <LinearProgress variant="determinate" value={pct} sx={{ flex: 1, height: 8, borderRadius: 4, bgcolor: "#e9ecef", "& .MuiLinearProgress-bar": { bgcolor: STATUS[p.status]?.color } }} />
                                  <Box sx={{ fontSize: 13, color: THEME.muted, whiteSpace: "nowrap" }}>{p.processes_done}/{p.processes}</Box>
                                </Stack>
                              </TableCell>
                              <TableCell>{p.current_process || "–"}{p.current_status && p.current_status !== "UPCOMING" && <Box sx={{ mt: 0.25 }}><StatusChip status={p.current_status} small /></Box>}</TableCell>
                              <TableCell><StatusChip status={p.status} /></TableCell>
                              <TableCell sx={{ whiteSpace: "nowrap", fontWeight: 600, color: p.variance_min > 0 ? STATUS.DONE_LATE.color : THEME.text }}>{fmtVariance(p.variance_min)}</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </>
              )}
              <HoverCard hover={hover} />
            </>
          ) : (
            tab !== 2 && tab !== 3 && !loading && !error && (
              <Box sx={{ textAlign: "center", p: 6, color: "#666", bgcolor: "#f8f9fa", borderRadius: "10px", fontSize: 15 }}>
                Pick a plant - the schedule is built automatically.
              </Box>
            )
          )}
        </Box>
      </Box>

      <Snackbar open={!!toast} autoHideDuration={6000} onClose={() => setToast(null)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        <Alert severity="success" variant="filled" onClose={() => setToast(null)} sx={{ fontSize: 15, alignItems: "center" }}
          action={toast?.planId ? <Button color="inherit" size="small" onClick={() => { setPlanId(toast.planId); setTab(2); setToast(null); }}>Open Planned vs Actual</Button> : undefined}>
          {toast?.text}
        </Alert>
      </Snackbar>
    </FsContext.Provider>
  );
}
