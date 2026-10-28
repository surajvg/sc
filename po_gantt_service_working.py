# # """
# # po_gantt_service.py  -  "PO on Station" Gantt grid

# #     GET /schedule/po-gantt           JSON grid: rows = stations, columns = working days,
# #                                      cells = the POs worked on that station that day
# #     GET /schedule/po-gantt/export    the same grid as .xlsx

# # Hook-up (Data_Server.py):
# #     from po_gantt_service import create_po_gantt_router
# #     app.include_router(create_po_gantt_router(init_db, verify_token, engine=engine))   # engine optional, see below

# # README / ASSUMPTIONS
# #  * Unit of work = the WHOLE PO (target_quantity). No lot size. A PO moves station to station as a block;
# #    different POs overlap freely on different stations (pipelining).
# #  * Everything comes from the DB: production_order_tracking (+ PcbData), product_workflow_mapping,
# #    process_flow_master, part_process_time, process_type, stage_schedule_config, stage_capacity,
# #    equipment_details, operator_step_mapping, operator_shift_assignment, shift_definition, bom_items,
# #    public_holidays, calendar_exceptions.
# #  * Station = one process step (flow_step_id). Machines = distinct equipment_details.machine_id (else 1 manual station).
# #  * Time per unit = part_process_time.machine_time (if the column exists and > 0) else man time
# #    (actual_time / sap_time, hours -> minutes). Fallbacks: routing process_time_seconds, then stage_capacity.manufacturing_time_mins,
# #    then 1 min + warning.  SERIES: qty * t.  BATCH: ceil(qty / batch_size) * t.  Plus setup_minutes once per PO run.
# #  * Shifts per station come from stage_capacity (group name first, then step name); default 2 x 7 h.
# #    Daily capacity per machine = shifts * hours_per_shift * 60 * day factor; the day window starts at shift_start (06:00).
# #  * Off days: WEEKLY_OFF_DAYS, ALT_SATURDAYS_OFF, public_holidays, calendar_exceptions "Holiday".
# #    calendar_exceptions "Working" = full day (even on a Sunday), "Half-Day" = 50 % of the window.
# #  * SMT Line (station_group, type LINE): the member steps are scheduled one after the other, each as its own station;
# #    they are only DISPLAYED as one row (union of POs per day, summed minutes/capacity, members[] for expanding).
# #  * Child -> main: bom_items (child P/N appears as a material of the main P/N, leading zeros ignored). A main PO's first
# #    station waits for the child PO(s) that supply it (FIFO by quantity). Child POs are scheduled before their main POs
# #    whatever the load order; labels (B1, B2...) always follow the LOAD order.
# #  * "Utilisation alert threshold" and "Pace batch release to bottleneck" are intentionally NOT implemented.
# #  * Default start = first working day on or after today.
# # """
# # import io
# # import math
# # import re
# # from collections import defaultdict
# # from datetime import date, datetime, time, timedelta
# # from typing import Any, Dict, List, Optional, Tuple

# # from fastapi import APIRouter, Depends, HTTPException, Query
# # from fastapi.responses import StreamingResponse
# # from sqlalchemy import Column, Integer, String
# # from sqlalchemy.orm import Session

# # from Database_models import (
# #     base, BOMItem, CalendarException, Equipments, OperatorLog, OperatorShiftAssignment, OperatorStepMapping,
# #     PartProcessTime, PcbData, ProcessFlowMaster, Processtype, ProductionOrderTracking, ProductTypeMaster,
# #     ProductWorkflowMapping, PublicHoliday, ShiftDefinition, StageCapacityDB, StageScheduleConfig,
# # )

# # # --------------------------------------------------------------------------------------
# # # Constants (change the rules in one place)
# # # --------------------------------------------------------------------------------------
# # ISO = "%Y-%m-%dT%H:%M:%S"
# # WEEKLY_OFF_DAYS = (6,)             # Python weekday(): Monday = 0 ... Sunday = 6
# # ALT_SATURDAYS_OFF = (1, 3)         # 1st and 3rd Saturday of the month
# # DEFAULT_SHIFTS = 2
# # DEFAULT_HOURS_PER_SHIFT = 7.0
# # DEFAULT_SHIFT_START = 6.0          # day window starts 06:00
# # DEFAULT_BATCH_SIZE = 30
# # FALLBACK_MINUTES = 1.0
# # NOT_STARTED_STATUSES = {"New", "Assigned"}
# # EXTRA_CHILD_LINKS: Dict[str, str] = {}      # {main_part_no: child_part_no} if bom_items does not show the link

# # SMT_LINE_NAME = "SMT Line"
# # # Fallback when station_group is empty: SOLDER PASTE PRINTING / INSPECTION, PICK N PLACE, REFLOW - BOTTOM SIDE
# # SMT_LINE_STEP_IDS = (10, 11, 12, 13)

# # BLUE, ORANGE = "BLUE", "ORANGE"


# # class PoGanttError(Exception):
# #     def __init__(self, status_code: int, detail: str):
# #         super().__init__(detail)
# #         self.status_code, self.detail = status_code, detail


# # # --------------------------------------------------------------------------------------
# # # The one new table: station_group
# # # --------------------------------------------------------------------------------------
# # class StationGroup(base):
# #     """Steps that are shown as ONE row (e.g. the SMT Line). They are still scheduled one after the other."""
# #     __tablename__ = "station_group"
# #     id = Column(Integer, primary_key=True, autoincrement=True)
# #     group_name = Column(String, nullable=False)
# #     flow_step_id = Column(Integer, nullable=False)
# #     group_type = Column(String, default="LINE")
# #     sort_order = Column(Integer, default=0)


# # def seed_station_group(db: Session) -> int:
# #     """Insert the SMT Line group (steps 10-13) if the table is empty. Returns rows inserted."""
# #     if db.query(StationGroup).count():
# #         return 0
# #     for i, sid in enumerate(SMT_LINE_STEP_IDS):
# #         db.add(StationGroup(group_name=SMT_LINE_NAME, flow_step_id=sid, group_type="LINE", sort_order=i))
# #     db.commit()
# #     return len(SMT_LINE_STEP_IDS)


# # # --------------------------------------------------------------------------------------
# # # Helpers
# # # --------------------------------------------------------------------------------------
# # def _iso(dt: datetime) -> str:
# #     return dt.replace(microsecond=0).strftime(ISO)


# # def _norm(s: Optional[str]) -> str:
# #     """Part / PO numbers: ignore spaces and leading zeros."""
# #     return (s or "").strip().lstrip("0")


# # def _key(s: Optional[str]) -> str:
# #     """Name matching: case / punctuation insensitive."""
# #     return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# # # --------------------------------------------------------------------------------------
# # # Calendar with a per-station daily window
# # # --------------------------------------------------------------------------------------
# # class DayCalendar:
# #     """A working day d has a window [d shift_start, +capacity*factor). A station's capacity decides the window length,
# #     so a 3-shift station gets a longer window than a 2-shift station. Windows never overlap (capacity <= 24 h)."""

# #     def __init__(self, holidays: Dict[date, str], exceptions: Dict[date, str], shift_start: float):
# #         self.holidays = holidays
# #         self.exceptions = {d: (t or "").strip().lower() for d, t in exceptions.items()}
# #         self.shift_start = float(shift_start)

# #     def factor(self, d: date) -> float:
# #         exc = self.exceptions.get(d)
# #         if exc == "working":
# #             return 1.0
# #         if exc == "half-day":
# #             return 0.5
# #         if exc == "holiday":
# #             return 0.0
# #         if d in self.holidays:
# #             return 0.0
# #         if d.weekday() in WEEKLY_OFF_DAYS:
# #             return 0.0
# #         if d.weekday() == 5 and ((d.day - 1) // 7 + 1) in ALT_SATURDAYS_OFF:
# #             return 0.0
# #         return 1.0

# #     def off_reason(self, d: date) -> str:
# #         if d in self.holidays:
# #             return self.holidays[d] or "Holiday"
# #         if self.exceptions.get(d) == "holiday":
# #             return "Holiday"
# #         if d.weekday() == 6:
# #             return "Sunday"
# #         if d.weekday() == 5:
# #             return "1st/3rd Saturday"
# #         return "Off"

# #     def window(self, d: date, cap_min: float) -> Tuple[datetime, datetime]:
# #         ws = datetime.combine(d, time.min) + timedelta(hours=self.shift_start)
# #         return ws, ws + timedelta(minutes=cap_min * self.factor(d))

# #     def first_working_day(self, d: date) -> date:
# #         for _ in range(4000):
# #             if self.factor(d) > 0:
# #                 return d
# #             d += timedelta(days=1)
# #         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

# #     def locate(self, t: datetime, cap_min: float) -> Tuple[datetime, date]:
# #         """Earliest moment >= t inside a working window, and the working day that window belongs to."""
# #         d = t.date() - timedelta(days=1)                      # yesterday's window may spill past midnight
# #         for _ in range(4000):
# #             if self.factor(d) > 0:
# #                 ws, we = self.window(d, cap_min)
# #                 if t < ws:
# #                     return ws, d
# #                 if t < we:
# #                     return t, d
# #             d += timedelta(days=1)
# #         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

# #     def consume(self, start: datetime, minutes: float, cap_min: float):
# #         """Run `minutes` of work from `start`, only inside working windows.
# #         Returns (real_start, end, end_day, [(day, minutes_used), ...])."""
# #         cur, day = self.locate(start, cap_min)
# #         first, rem, usage = cur, float(minutes), []
# #         for _ in range(100000):
# #             _, we = self.window(day, cap_min)
# #             use = min(rem, (we - cur).total_seconds() / 60.0)
# #             if use > 0:
# #                 usage.append((day, use))
# #             rem -= use
# #             cur += timedelta(minutes=use)
# #             if rem <= 1e-9:
# #                 return first, cur, day, usage
# #             cur, day = self.locate(we, cap_min)
# #         raise PoGanttError(500, "Could not place a run inside the working calendar")


# # # --------------------------------------------------------------------------------------
# # # Station / PO containers
# # # --------------------------------------------------------------------------------------
# # class Station:
# #     def __init__(self, sid: int, name: str):
# #         self.sid, self.name = sid, name
# #         self.machines: List[str] = []
# #         self.shifts, self.hps, self.cap_min = DEFAULT_SHIFTS, DEFAULT_HOURS_PER_SHIFT, 0.0
# #         self.mode, self.batch_size = "SERIES", DEFAULT_BATCH_SIZE
# #         self.setup = self.cooldown = 0.0
# #         self.cd_working_only = self.next_day_release = False
# #         self.operators = 0
# #         self.parts: List[str] = []
# #         self.role = "MAIN"
# #         self.group: Optional[str] = None


# # # --------------------------------------------------------------------------------------
# # # Builder
# # # --------------------------------------------------------------------------------------
# # # def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
# # #     """Every PO in the DB (tracking table + PcbData), keyed by normalised PO number."""
# # #     q = db.query(ProductionOrderTracking)
# # #     if plant:
# # #         q = q.filter(ProductionOrderTracking.plant_code == plant)
# # #     tracked = q.order_by(ProductionOrderTracking.created_at, ProductionOrderTracking.po_number).all()

# # #     pq = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt
# # #                   ).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
# # #     if plant:
# # #         pq = pq.filter(PcbData.plant == plant)
# # #     pcb_by_po: Dict[str, list] = defaultdict(list)
# # #     for r in pq.all():
# # #         pcb_by_po[_norm(r[0])].append(r)

# # #     logged = {_norm(r[0]) for r in db.query(PcbData.productionOrder).join(
# # #         OperatorLog, OperatorLog.PCBserialNoPartNumber == PcbData.PCBserialNoPartNumber
# # #     ).filter(PcbData.productionOrder.isnot(None)).distinct().all()}

# # #     cands: Dict[str, Dict[str, Any]] = {}
# # #     for t in tracked:
# # #         k = _norm(t.po_number) or t.po_number
# # #         started = ((t.status or "").strip().lower() not in NOT_STARTED_STATUSES
# # #                    or (t.completed_quantity or 0) > 0 or (t.rework_quantity or 0) > 0 or (t.scrap_quantity or 0) > 0)
# # #         cands[k] = {"po": k, "part": t.part_number, "qty": int(t.target_quantity or 0),
# # #                     "created": t.created_at, "started": started, "logged": k in logged}
# # #     for k, rows in pcb_by_po.items():
# # #         qty = sum((r[2] if (r[2] and r[2] > 0) else 1) for r in rows)
# # #         pcb_started = any((r[3] or "").strip().lower() not in NOT_STARTED_STATUSES for r in rows)
# # #         parts = [r[1] for r in rows if r[1]]
# # #         if k in cands:
# # #             c = cands[k]
# # #             c["qty"] = c["qty"] or qty
# # #             c["part"] = c["part"] or (max(set(parts), key=parts.count) if parts else None)
# # #             c["started"] = c["started"] or pcb_started
# # #             continue
# # #         if not parts:
# # #             warnings.append(f"PO {k}: PCBs have no part number - ignored")
# # #             continue
# # #         created = [r[4] for r in rows if r[4]]
# # #         cands[k] = {"po": k, "part": max(set(parts), key=parts.count), "qty": qty,
# # #                     "created": min(created) if created else None, "started": pcb_started, "logged": k in logged}
# # #     return cands

# # # --- constant (replaces NOT_STARTED_STATUSES) ---
# # PCB_OPEN_STATUSES = {"new"}      # PcbData.status values that count as "not started"


# # # --- loader (replaces _load_candidates) ---
# # def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
# #     """POs come ONLY from PcbData. A PO is loadable when EVERY one of its PCBs has status New or Assigned."""
# #     q = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt
# #                  ).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
# #     if plant:
# #         q = q.filter(PcbData.plant == plant)
# #     by_po: Dict[str, list] = defaultdict(list)
# #     for r in q.all():
# #         by_po[_norm(r[0])].append(r)

# #     cands: Dict[str, Dict[str, Any]] = {}
# #     for po, rows in by_po.items():
# #         parts = [r[1] for r in rows if r[1]]
# #         if not parts:
# #             warnings.append(f"PO {po}: PCBs have no part number - ignored")
# #             continue
# #         part = max(set(parts), key=parts.count)
# #         if len(set(parts)) > 1:
# #             warnings.append(f"PO {po}: PCBs carry several part numbers ({', '.join(sorted(set(parts)))}) - {part} used")
# #         created = [r[4] for r in rows if r[4]]
# #         cands[po] = {
# #             "po": po, "part": part,
# #             "qty": sum(r[2] if (r[2] and r[2] > 0) else 1 for r in rows),          # one row per PCB
# #             "created": min(created) if created else None,
# #             "started": any((r[3] or "").strip().lower() not in PCB_OPEN_STATUSES for r in rows),
# #             "logged": False,
# #         }
# #     return cands


# # def build_po_gantt(db: Session, production_orders: Optional[List[str]] = None, plant: Optional[str] = None,
# #                    start_date: Optional[date] = None, time_source: str = "actual", label_mode: str = "seq",
# #                    show_holidays: bool = False, shift_start: float = DEFAULT_SHIFT_START,
# #                    today: Optional[date] = None) -> Dict[str, Any]:
# #     if time_source not in ("actual", "sap"):
# #         raise PoGanttError(400, "time_source must be 'actual' or 'sap'")
# #     if label_mode not in ("seq", "po"):
# #         raise PoGanttError(400, "label_mode must be 'seq' or 'po'")
# #     warnings: List[str] = []
# #     today = today or date.today()

# #     # ---------------- calendar ----------------
# #     holidays = {h.holiday_date: h.name for h in db.query(PublicHoliday).all()}
# #     exceptions = {e.exception_date: e.exception_type for e in db.query(CalendarException).all()}
# #     cal = DayCalendar(holidays, exceptions, shift_start)

# #     # ---------------- masters (loaded once) ----------------
# #     stages = {s.flow_step_id: s for s in db.query(ProcessFlowMaster).all()}
# #     is_batch: Dict[int, bool] = defaultdict(bool)
# #     for p in db.query(Processtype).all():
# #         if p.process_type_batch:
# #             is_batch[p.stage_id] = True
# #     cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
# #     cap_by_key = {_key(c.name): c for c in db.query(StageCapacityDB).all()}
# #     products = {p.part_number: p for p in db.query(ProductTypeMaster).all()}
# #     part_by_norm = {_norm(pn): pn for pn in products}

# #     equipment: Dict[int, List[str]] = defaultdict(list)
# #     for e in db.query(Equipments).order_by(Equipments.stage_id, Equipments.id).all():
# #         mid = e.machine_id or e.eqpt_no or f"EQ-{e.id}"
# #         if e.stage_id is not None and mid not in equipment[e.stage_id]:
# #             equipment[e.stage_id].append(mid)

# #     shift_names = [s.name for s in db.query(ShiftDefinition).filter(ShiftDefinition.is_active.is_(True))
# #                    .order_by(ShiftDefinition.sort_order, ShiftDefinition.id).all()]
# #     assigned: Dict[str, set] = defaultdict(set)
# #     for a in db.query(OperatorShiftAssignment).all():
# #         assigned[a.operator_staff_no].add(a.shift_name)
# #     ops_by_stage: Dict[int, List[str]] = defaultdict(list)
# #     for o in db.query(OperatorStepMapping).all():
# #         who = o.operator_staff_no or o.operator_name
# #         if who and who not in ops_by_stage[o.flow_step_id]:
# #             ops_by_stage[o.flow_step_id].append(who)

# #     def operators_per_shift(sid: int) -> int:
# #         ops = ops_by_stage.get(sid, [])
# #         if not shift_names:
# #             return len(ops)
# #         return max((sum(1 for o in ops if not assigned.get(o) or sn in assigned[o]) for sn in shift_names), default=0)

# #     # station groups (display only)
# #     try:
# #         grows = db.query(StationGroup).filter(StationGroup.group_type == "LINE").order_by(
# #             StationGroup.group_name, StationGroup.sort_order, StationGroup.id).all()
# #     except Exception:                                           # table not created yet
# #         db.rollback()
# #         grows = []
# #     groups: Dict[str, List[int]] = defaultdict(list)
# #     for g in grows:
# #         groups[g.group_name].append(g.flow_step_id)
# #     if not groups:
# #         groups[SMT_LINE_NAME] = list(SMT_LINE_STEP_IDS)
# #     group_of = {sid: name for name, ids in groups.items() for sid in ids}

# #     # child -> main links
# #     child_of: Dict[str, str] = {}
# #     for main_pn, material in db.query(BOMItem.product_part_number, BOMItem.material).all():
# #         c = part_by_norm.get(_norm(material))
# #         if c and main_pn and c != main_pn:
# #             child_of.setdefault(main_pn, c)
# #     for m, c in EXTRA_CHILD_LINKS.items():
# #         m, c = part_by_norm.get(_norm(m)), part_by_norm.get(_norm(c))
# #         if m and c:
# #             child_of[m] = c
# #     for m, c in list(child_of.items()):
# #         if child_of.get(c) == m:
# #             del child_of[m]
# #     child_parts = set(child_of.values())

# #     # ---------------- select the POs to load ----------------
# #     cands = _load_candidates(db, plant, warnings)
# #     if production_orders:
# #         selected, seen = [], set()
# #         for raw in production_orders:
# #             k = _norm(raw) or raw
# #             if k in seen:
# #                 continue
# #             seen.add(k)
# #             if k not in cands:
# #                 raise PoGanttError(404, f"Production order {raw} not found")
# #             if cands[k]["started"] or cands[k]["logged"]:
# #                 warnings.append(f"PO {k} has already started - scheduled from scratch as requested")
# #             selected.append(cands[k])
# #         explicit = True
# #     else:
# #         selected = sorted((c for c in cands.values() if not c["started"] and not c["logged"]),
# #                           key=lambda c: (c["created"] or datetime.max, c["po"]))
# #         explicit = False

# #     # ---------------- routing + times ----------------
# #     part_numbers = {c["part"] for c in selected if c["part"]}
# #     routing: Dict[str, list] = defaultdict(list)
# #     times: Dict[tuple, list] = defaultdict(list)
# #     if part_numbers:
# #         for r in db.query(ProductWorkflowMapping).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
# #                 ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
# #                            ProductWorkflowMapping.id).all():
# #             routing[r.product_part_number].append(r)
# #         for r in db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(part_numbers)).all():
# #             times[(r.part_no, r.process_id)].append(r)
# #     other = "sap" if time_source == "actual" else "actual"

# #     def hours_per_unit(part: str, step) -> Tuple[Optional[float], str]:
# #         rows = times.get((part, step.flow_step_id), [])
# #         if rows:
# #             plant_code = products[part].plant_code if part in products else None
# #             row = next((r for r in rows if r.plant == plant_code), rows[0])
# #             mt = getattr(row, "machine_time", None)            # column is added later -> getattr
# #             if mt and mt > 0:
# #                 return float(mt), "machine_time"
# #             for src in (time_source, other):
# #                 val = row.actual_time if src == "actual" else row.sap_time
# #                 if val and val > 0:
# #                     return float(val), f"part_process_time.{src}"
# #         if step.process_time_seconds and step.process_time_seconds > 0:
# #             return step.process_time_seconds / 3600.0, "routing"
# #         stage = stages.get(step.flow_step_id)
# #         cap = cap_by_key.get(_key(stage.step_name)) if stage else None
# #         if cap and cap.manufacturing_time_mins and cap.manufacturing_time_mins > 0:
# #             return float(cap.manufacturing_time_mins) / 60.0, "stage_capacity"
# #         return None, "none"

# #     def capacity_for(names: List[str]) -> Optional[Tuple[int, float]]:
# #         for n in names:
# #             c = cap_by_key.get(_key(n))
# #             if c:
# #                 sh = int(c.shifts_per_day or 0)
# #                 hp = float(c.hours_per_shift or 0)
# #                 return (sh if sh > 0 else DEFAULT_SHIFTS), (hp if hp > 0 else DEFAULT_HOURS_PER_SHIFT)
# #         return None

# #     # ---------------- build PO objects ----------------
# #     pos: List[Dict[str, Any]] = []
# #     for c in selected:
# #         part, po_no = c["part"], c["po"]
# #         steps = routing.get(part or "", [])
# #         if not steps or c["qty"] <= 0:
# #             msg = (f"PO {po_no}: part {part} has no routing in product_workflow_mapping" if not steps
# #                    else f"PO {po_no}: target quantity is 0")
# #             if explicit:
# #                 raise PoGanttError(422, msg)
# #             warnings.append(msg + " - not scheduled")
# #             continue
# #         pos.append({"po": po_no, "part": part, "qty": c["qty"], "steps": steps, "idx": len(pos) + 1,
# #                     "role": "CHILD" if part in child_parts else "MAIN"})
# #     if not pos:
# #         raise PoGanttError(404, "No production orders to schedule")
# #     for p in pos:
# #         p["label"] = f"B{p['idx']}" if label_mode == "seq" else p["po"]
# #     label_idx = {p["label"]: p["idx"] for p in pos}

# #     # ---------------- stations (flow order: child part first, then main) ----------------
# #     def depth(part: str) -> int:
# #         d = 0
# #         while part in child_of and d < 10:
# #             part, d = child_of[part], d + 1
# #         return d

# #     scheduled_parts = {p["part"] for p in pos}
# #     tops = sorted(pt for pt in scheduled_parts | set(child_of) if pt not in child_parts)
# #     part_order: List[str] = []
# #     for top in tops:
# #         chain, pt = [], top
# #         while pt and pt not in chain:
# #             chain.append(pt)
# #             pt = child_of.get(pt)
# #         for pt in reversed(chain):
# #             if pt in scheduled_parts and pt not in part_order:
# #                 part_order.append(pt)
# #     part_order += sorted(pt for pt in scheduled_parts if pt not in part_order)

# #     stations: Dict[int, Station] = {}
# #     flow_order: List[int] = []
# #     for part in part_order:
# #         for st_row in routing.get(part, []):
# #             sid = st_row.flow_step_id
# #             if sid not in stations:
# #                 stage = stages.get(sid)
# #                 s = Station(sid, stage.step_name if stage else f"Step {sid}")
# #                 s.group = group_of.get(sid)
# #                 s.mode = "BATCH" if is_batch.get(sid) else "SERIES"
# #                 c = cfg.get(sid)
# #                 if c:
# #                     s.batch_size = max(int(c.batch_size or DEFAULT_BATCH_SIZE), 1)
# #                     s.setup = float(c.setup_minutes or 0)
# #                     s.cooldown = float(c.cooldown_minutes or 0)
# #                     s.cd_working_only = bool(c.cooldown_working_time_only)
# #                     s.next_day_release = bool(c.next_day_release) and s.mode == "BATCH"
# #                 names = ([s.group] if s.group else []) + [s.name]
# #                 got = capacity_for(names)
# #                 if got:
# #                     s.shifts, s.hps = got
# #                 s.cap_min = min(s.shifts * s.hps * 60.0, 1440.0)
# #                 s.machines = list(equipment.get(sid, [])) or [f"MANUAL-{sid}"]
# #                 s.operators = operators_per_shift(sid)
# #                 s.role = "CHILD" if part in child_parts else "MAIN"
# #                 stations[sid] = s
# #                 flow_order.append(sid)
# #             if part not in stations[sid].parts:
# #                 stations[sid].parts.append(part)

# #     # ---------------- child PO -> main PO supply (FIFO by quantity) ----------------
# #     depends_on: Dict[str, List[str]] = defaultdict(list)
# #     by_part: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# #     for p in pos:
# #         by_part[p["part"]].append(p)
# #     for main_pn, child_pn in child_of.items():
# #         mains, childs = by_part.get(main_pn, []), by_part.get(child_pn, [])
# #         if not mains:
# #             continue
# #         if not childs:
# #             warnings.append(f"Part {main_pn}: no child PO ({child_pn}) loaded - child PCBs assumed in stock, "
# #                             f"main PO(s) {', '.join(m['label'] for m in mains)} start right away")
# #             continue
# #         supply, run = [], 0
# #         for c in childs:
# #             supply.append((run, run + c["qty"], c["po"]))
# #             run += c["qty"]
# #         need = 0
# #         for m in mains:
# #             lo, hi = need, need + m["qty"]
# #             need = hi
# #             depends_on[m["po"]] = [cpo for (a, b, cpo) in supply if a < hi and b > lo]
# #             if hi > run:
# #                 warnings.append(f"PO {m['po']}: needs more child PCBs than the loaded child POs provide - rest assumed in stock")

# #     # ---------------- schedule (finite capacity) ----------------
# #     start_day = cal.first_working_day(start_date or today)
# #     start_dt = datetime.combine(start_day, time.min) + timedelta(hours=shift_start)
# #     default_cap = min(DEFAULT_SHIFTS * DEFAULT_HOURS_PER_SHIFT * 60.0, 1440.0)

# #     free_at: Dict[Tuple[int, str], datetime] = defaultdict(lambda: datetime.min)
# #     usage: Dict[int, Dict[date, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
# #     runs: Dict[Tuple[int, str], List[datetime]] = {}
# #     po_ready: Dict[str, datetime] = {}
# #     po_span: Dict[str, List[datetime]] = {}
# #     missing_time: Dict[str, List[str]] = defaultdict(list)

# #     for p in sorted(pos, key=lambda x: (depth(x["part"]), x["idx"])):
# #         prev_ready = max([start_dt] + [po_ready[c] for c in depends_on.get(p["po"], []) if c in po_ready])
# #         for step in p["steps"]:
# #             st = stations[step.flow_step_id]
# #             hrs, _src = hours_per_unit(p["part"], step)
# #             if hrs is None:
# #                 missing_time[p["part"]].append(st.name)
# #                 minutes = FALLBACK_MINUTES
# #             elif st.mode == "BATCH":
# #                 minutes = math.ceil(p["qty"] / st.batch_size) * hrs * 60.0
# #             else:
# #                 minutes = p["qty"] * hrs * 60.0
# #             minutes = max(minutes + st.setup, 1.0)

# #             best = None
# #             for mid in st.machines:
# #                 s0 = max(prev_ready, free_at[(st.sid, mid)])
# #                 s, e, eday, use = cal.consume(s0, minutes, st.cap_min)
# #                 if best is None or e < best[2]:
# #                     best = (mid, s, e, eday, use)
# #             mid, s, e, eday, use = best
# #             free_at[(st.sid, mid)] = e
# #             for d, mins in use:
# #                 usage[st.sid][d][p["label"]] += mins
# #             span = runs.setdefault((st.sid, p["label"]), [s, e])
# #             span[0], span[1] = min(span[0], s), max(span[1], e)
# #             ps = po_span.setdefault(p["po"], [s, e])
# #             ps[0], ps[1] = min(ps[0], s), max(ps[1], e)

# #             ready = e                                            # when the PO may enter the next station
# #             if st.next_day_release:
# #                 ready = datetime.combine(cal.first_working_day(eday + timedelta(days=1)), time.min) + timedelta(hours=shift_start)
# #             if st.cooldown > 0:
# #                 if st.cd_working_only:
# #                     ready = cal.consume(ready, st.cooldown, default_cap)[1]
# #                 else:
# #                     ready = ready + timedelta(minutes=st.cooldown)
# #             prev_ready = ready
# #         po_ready[p["po"]] = prev_ready

# #     for part, names in missing_time.items():
# #         uniq = list(dict.fromkeys(names))
# #         warnings.append(f"Part {part}: no process time for {len(uniq)} step(s) "
# #                         f"[{', '.join(uniq[:6])}{'...' if len(uniq) > 6 else ''}] - {FALLBACK_MINUTES:g} min used")

# #     # ---------------- days ----------------
# #     used_days = [d for per_day in usage.values() for d in per_day]
# #     last_day = max(used_days + [start_day])
# #     days, day_no, working_nos = [], {}, 0
# #     d = start_day
# #     while d <= last_day:
# #         if cal.factor(d) > 0:
# #             working_nos += 1
# #             day_no[d] = working_nos
# #             days.append({"working_day_no": working_nos, "date": d.isoformat(), "weekday": d.strftime("%a"),
# #                          "is_holiday": False, "off_reason": None})
# #         elif show_holidays:
# #             days.append({"working_day_no": None, "date": d.isoformat(), "weekday": d.strftime("%a"),
# #                          "is_holiday": True, "off_reason": cal.off_reason(d)})
# #         d += timedelta(days=1)

# #     # ---------------- rows ----------------
# #     def order_labels(labels) -> List[str]:
# #         return sorted(labels, key=lambda x: label_idx.get(x, 0))

# #     def cells_for(sids: List[int]) -> List[Dict[str, Any]]:
# #         out = []
# #         for dd, no in day_no.items():
# #             labels, used, capacity = set(), 0.0, 0.0
# #             for sid in sids:
# #                 s = stations[sid]
# #                 capacity += len(s.machines) * s.cap_min * cal.factor(dd)
# #                 u = usage.get(sid, {}).get(dd)
# #                 if u:
# #                     used += sum(u.values())
# #                     labels.update(u)
# #             if labels:
# #                 out.append({"working_day_no": no, "date": dd.isoformat(), "pos": order_labels(labels),
# #                             "color": ORANGE if len(labels) >= 2 else BLUE,
# #                             "minutes_used": round(used, 1), "capacity_minutes": round(capacity, 1)})
# #         return out

# #     def runs_for(sids: List[int]) -> List[Dict[str, str]]:
# #         merged: Dict[str, List[datetime]] = {}
# #         for (sid, label), (s, e) in runs.items():
# #             if sid in sids:
# #                 cur = merged.setdefault(label, [s, e])
# #                 cur[0], cur[1] = min(cur[0], s), max(cur[1], e)
# #         return [{"label": lb, "start": _iso(v[0]), "end": _iso(v[1])}
# #                 for lb, v in sorted(merged.items(), key=lambda kv: (kv[1][0], label_idx.get(kv[0], 0)))]

# #     rows: List[Dict[str, Any]] = []
# #     done_groups = set()
# #     for sid in flow_order:
# #         s = stations[sid]
# #         if s.group and s.group in done_groups:
# #             continue
# #         if not s.group:
# #             rows.append({"station_id": f"STEP-{sid}", "name": s.name, "flow_step_id": sid,
# #                          "part_number": s.parts[0], "part_numbers": s.parts, "role": s.role,
# #                          "shifts": s.shifts, "mins_per_shift": int(s.hps * 60), "machines": len(s.machines),
# #                          "operators_per_shift": s.operators, "process_mode": s.mode,
# #                          "cells": cells_for([sid]), "po_runs": runs_for([sid])})
# #             continue
# #         done_groups.add(s.group)
# #         members = [stations[m] for m in flow_order if stations[m].group == s.group]
# #         gcap = capacity_for([s.group])
# #         lead = max(members, key=lambda m: m.shifts)
# #         shifts, hps = gcap if gcap else (lead.shifts, lead.hps)
# #         mids = [m.sid for m in members]
# #         rows.append({"station_id": f"GROUP-{s.group}", "name": s.group, "part_number": members[0].parts[0],
# #                      "part_numbers": sorted({pt for m in members for pt in m.parts}), "role": members[0].role,
# #                      "shifts": shifts, "mins_per_shift": int(hps * 60),
# #                      "machines": max(len(m.machines) for m in members),
# #                      "operators_per_shift": max(m.operators for m in members), "process_mode": "LINE",
# #                      "cells": cells_for(mids), "po_runs": runs_for(mids),
# #                      "members": [{"step_name": m.name, "flow_step_id": m.sid, "shifts": m.shifts,
# #                                   "machines": len(m.machines), "process_mode": m.mode,
# #                                   "cells": cells_for([m.sid]), "po_runs": runs_for([m.sid])} for m in members]})

# #     assumptions = [
# #         "Unit of work is the whole PO (target quantity); POs move through the stations as a block.",
# #         f"Shifts per station come from stage_capacity (default {DEFAULT_SHIFTS} x {DEFAULT_HOURS_PER_SHIFT:g} h); the day starts at {_hm(shift_start)}.",
# #         "Off days: Sundays, 1st and 3rd Saturdays, public holidays and calendar 'Holiday' exceptions; 'Working' reopens a day, 'Half-Day' halves it.",
# #         f"Time per unit = machine time if present, else {'actual' if time_source == 'actual' else 'SAP'} man time (fallback to the other, routing, stage_capacity).",
# #         "SMT Line steps are scheduled one after the other and only shown as one row.",
# #         "Operators per shift is informational; it does not limit the schedule.",
# #     ]
# #     return {
# #         "meta": {
# #             "number_of_pos": len(pos), "start_date": start_day.isoformat(), "finish_date": last_day.isoformat(),
# #             "working_days": working_nos, "time_source": time_source, "label_mode": label_mode,
# #             "pos": [{"label": p["label"], "production_order": p["po"], "part_number": p["part"], "role": p["role"],
# #                      "quantity": p["qty"], "depends_on": depends_on.get(p["po"], []),
# #                      "start": _iso(po_span[p["po"]][0]), "end": _iso(po_span[p["po"]][1])} for p in pos],
# #         },
# #         "days": days, "stations": rows, "warnings": warnings, "assumptions": assumptions,
# #     }


# # def _hm(h: float) -> str:
# #     hh = int(h)
# #     return f"{hh:02d}:{int(round((h - hh) * 60)):02d}"


# # # --------------------------------------------------------------------------------------
# # # Excel export
# # # --------------------------------------------------------------------------------------
# # def build_po_gantt_xlsx(result: Dict[str, Any]) -> bytes:
# #     from openpyxl import Workbook
# #     from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
# #     from openpyxl.utils import get_column_letter

# #     font = lambda **kw: Font(name="Arial", size=10, **kw)
# #     thin = Side(style="thin", color="BFBFBF")
# #     border = Border(left=thin, right=thin, top=thin, bottom=thin)
# #     head = PatternFill("solid", start_color="DDE3EE")
# #     off = PatternFill("solid", start_color="D9D9D9")
# #     fills = {BLUE: PatternFill("solid", start_color="9FC5E8"), ORANGE: PatternFill("solid", start_color="F6B26B")}
# #     center = Alignment(horizontal="center", vertical="center", wrap_text=True)

# #     wb = Workbook()
# #     ws = wb.active
# #     ws.title = "PO on Station"
# #     days = result["days"]
# #     ws.column_dimensions["A"].width = 30
# #     ws.column_dimensions["B"].width = 10
# #     for i, label in enumerate(("Working day #", "Date", "Day"), start=1):
# #         c = ws.cell(row=i, column=1, value=label)
# #         c.font, c.fill, c.border = font(bold=True), head, border
# #         ws.cell(row=i, column=2).fill = head
# #         ws.cell(row=i, column=2).border = border
# #     for j, d in enumerate(days, start=3):
# #         ws.column_dimensions[get_column_letter(j)].width = 11
# #         dt = date.fromisoformat(d["date"])
# #         vals = ("Off" if d["is_holiday"] else d["working_day_no"], dt.strftime("%d-%b"), d["weekday"])
# #         for i, v in enumerate(vals, start=1):
# #             c = ws.cell(row=i, column=j, value=v)
# #             c.font, c.border, c.alignment = font(bold=(i == 1)), border, center
# #             c.fill = off if d["is_holiday"] else head
# #     col_of = {d["working_day_no"]: j for j, d in enumerate(days, start=3) if d["working_day_no"]}
# #     for r, st in enumerate(result["stations"], start=4):
# #         a = ws.cell(row=r, column=1, value=st["name"])
# #         a.font, a.border = font(bold=True), border
# #         b = ws.cell(row=r, column=2, value=f"{st['shifts']} shift")
# #         b.font, b.border, b.alignment = font(), border, center
# #         for j, d in enumerate(days, start=3):
# #             c = ws.cell(row=r, column=j)
# #             c.border = border
# #             if d["is_holiday"]:
# #                 c.fill = off
# #         for cell in st["cells"]:
# #             c = ws.cell(row=r, column=col_of[cell["working_day_no"]], value=" ".join(cell["pos"]))
# #             c.fill, c.font, c.alignment = fills[cell["color"]], font(bold=True), center
# #     r = 4 + len(result["stations"]) + 1
# #     ws.cell(row=r, column=1, value="Legend").font = font(bold=True)
# #     for k, (lab, txt, col) in enumerate((("Blue", "1 PO on the station", BLUE), ("Orange", "2 or more POs share the station", ORANGE)), 1):
# #         ws.cell(row=r + k, column=1, value=f"{lab}: {txt}").font = font()
# #         ws.cell(row=r + k, column=2).fill = fills[col]
# #     r += 4
# #     for j, h in enumerate(("Label", "Production order", "Part number", "Role", "Quantity", "Start", "End"), start=1):
# #         c = ws.cell(row=r, column=j, value=h)
# #         c.font, c.fill, c.border = font(bold=True), head, border
# #     for k, p in enumerate(result["meta"]["pos"], start=1):
# #         for j, v in enumerate((p["label"], p["production_order"], p["part_number"], p["role"], p["quantity"],
# #                                p["start"], p["end"]), start=1):
# #             c = ws.cell(row=r + k, column=j, value=v)
# #             c.font, c.border = font(), border
# #     ws.freeze_panes = "C4"
# #     buf = io.BytesIO()
# #     wb.save(buf)
# #     return buf.getvalue()


# # # --------------------------------------------------------------------------------------
# # # Router
# # # --------------------------------------------------------------------------------------
# # def create_po_gantt_router(init_db, verify_token=None, engine=None) -> APIRouter:
# #     """engine (optional): creates the station_group table if missing and seeds the SMT Line group."""
# #     router = APIRouter()
# #     deps = [Depends(verify_token)] if verify_token else []
# #     if engine is not None:
# #         StationGroup.__table__.create(bind=engine, checkfirst=True)
# #         from sqlalchemy.orm import sessionmaker
# #         with sessionmaker(bind=engine)() as s:
# #             seed_station_group(s)

# #     def _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start):
# #         try:
# #             return build_po_gantt(db, production_order, plant, start_date, time_source, label_mode,
# #                                   show_holidays, shift_start)
# #         except PoGanttError as e:
# #             raise HTTPException(status_code=e.status_code, detail=e.detail)

# #     @router.get("/schedule/po-gantt", dependencies=deps)
# #     def po_gantt(
# #         production_order: Optional[List[str]] = Query(None, description="PO numbers to load; order = load priority"),
# #         plant: Optional[str] = Query(None),
# #         start_date: Optional[date] = Query(None, description="default: first working day on/after today"),
# #         time_source: str = Query("actual"),
# #         label_mode: str = Query("seq", description="'seq' = B1, B2... | 'po' = PO number"),
# #         show_holidays: bool = Query(False, description="show off days as empty flagged columns"),
# #         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=10),
# #         db: Session = Depends(init_db),
# #     ):
# #         return _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)

# #     @router.get("/schedule/po-gantt/export", dependencies=deps)
# #     def po_gantt_export(
# #         production_order: Optional[List[str]] = Query(None),
# #         plant: Optional[str] = Query(None),
# #         start_date: Optional[date] = Query(None),
# #         time_source: str = Query("actual"),
# #         label_mode: str = Query("seq"),
# #         show_holidays: bool = Query(False),
# #         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=10),
# #         db: Session = Depends(init_db),
# #     ):
# #         result = _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)
# #         return StreamingResponse(
# #             io.BytesIO(build_po_gantt_xlsx(result)),
# #             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
# #             headers={"Content-Disposition": 'attachment; filename="po_gantt.xlsx"'},
# #         )

# #     return router





# """
# po_gantt_service.py  -  "PO on Station" Gantt grid

#     GET /schedule/po-gantt           JSON grid: rows = stations, columns = working days,
#                                      cells = the POs worked on that station that day
#     GET /schedule/po-gantt/export    the same grid as .xlsx

# Hook-up (Data_Server.py):
#     from po_gantt_service import create_po_gantt_router
#     app.include_router(create_po_gantt_router(init_db, verify_token, engine=engine))   # engine optional, see below

# README / ASSUMPTIONS
#  * Unit of work = the WHOLE PO (target_quantity). No lot size. A PO moves station to station as a block;
#    different POs overlap freely on different stations (pipelining).
#  * POs come ONLY from PcbData: a PO is loadable when all its PCBs are New/Assigned; quantity = sum of PCB quantity.
#    production_order_tracking is not read. Everything else comes from the DB too: product_workflow_mapping,
#    process_flow_master, part_process_time, process_type, stage_schedule_config, stage_capacity,
#    equipment_details, operator_step_mapping, operator_shift_assignment, shift_definition, bom_items,
#    public_holidays, calendar_exceptions.
#  * Station = one process step (flow_step_id). Machines = distinct equipment_details.machine_id (else 1 manual station).
#  * Time per unit = part_process_time.machine_time (if the column exists and > 0) else man time
#    (actual_time / sap_time, hours -> minutes). Fallbacks: routing process_time_seconds, then stage_capacity.manufacturing_time_mins,
#    then 1 min + warning.  SERIES: qty * t.  BATCH: ceil(qty / batch_size) * t.  Plus setup_minutes once per PO run.
#  * Shifts per station come from stage_capacity (group name first, then step name); default 2 x 7 h.
#    Daily capacity per machine = shifts * hours_per_shift * 60 * day factor; the day window starts at shift_start (06:00).
#  * Off days: WEEKLY_OFF_DAYS, ALT_SATURDAYS_OFF, public_holidays, calendar_exceptions "Holiday".
#    calendar_exceptions "Working" = full day (even on a Sunday), "Half-Day" = 50 % of the window.
#  * SMT Line (station_group, type LINE): the member steps are scheduled one after the other, each as its own station;
#    they are only DISPLAYED as one row (union of POs per day, summed minutes/capacity, members[] for expanding).
#  * Child -> main: bom_items (child P/N appears as a material of the main P/N, leading zeros ignored). A main PO's first
#    station waits for the child PO(s) that supply it (FIFO by quantity). Child POs are scheduled before their main POs
#    whatever the load order; labels (B1, B2...) always follow the LOAD order.
#  * "Utilisation alert threshold" and "Pace batch release to bottleneck" are intentionally NOT implemented.
#  * Default start = first working day on or after today.
# """
# import io
# import math
# import re
# from collections import defaultdict
# from datetime import date, datetime, time, timedelta
# from typing import Any, Dict, List, Optional, Tuple

# from fastapi import APIRouter, Depends, HTTPException, Query
# from fastapi.responses import StreamingResponse
# from sqlalchemy import Column, Integer, String
# from sqlalchemy.orm import Session, joinedload

# from Database_models import (
#     base, BOMItem, CalendarException, Equipments, OperatorShiftAssignment, OperatorStepMapping,
#     PartProcessTime, PcbData, ProcessFlowMaster, Processtype, ProductTypeMaster,
#     ProductWorkflowMapping, PublicHoliday, ShiftDefinition, StageCapacityDB, StageScheduleConfig,
# )

# # --------------------------------------------------------------------------------------
# # Constants (change the rules in one place)
# # --------------------------------------------------------------------------------------
# ISO = "%Y-%m-%dT%H:%M:%S"
# WEEKLY_OFF_DAYS = (6,)             # Python weekday(): Monday = 0 ... Sunday = 6
# ALT_SATURDAYS_OFF = (1, 3)         # 1st and 3rd Saturday of the month
# DEFAULT_SHIFTS = 2
# DEFAULT_HOURS_PER_SHIFT = 7.0
# DEFAULT_SHIFT_START = 6.0          # day window starts 06:00
# DEFAULT_BATCH_SIZE = 30
# FALLBACK_MINUTES = 1.0
# PCB_OPEN_STATUSES = {"new", "assigned"}      # PcbData.status values that count as "not started"
# EXTRA_CHILD_LINKS: Dict[str, str] = {}      # {main_part_no: child_part_no} if bom_items does not show the link

# SMT_LINE_NAME = "SMT Line"
# # Fallback when station_group is empty: SOLDER PASTE PRINTING / INSPECTION, PICK N PLACE, REFLOW - BOTTOM SIDE
# SMT_LINE_STEP_IDS = (10, 11, 12, 13)

# BLUE, ORANGE = "BLUE", "ORANGE"


# class PoGanttError(Exception):
#     def __init__(self, status_code: int, detail: str):
#         super().__init__(detail)
#         self.status_code, self.detail = status_code, detail


# # --------------------------------------------------------------------------------------
# # The one new table: station_group
# # --------------------------------------------------------------------------------------
# class StationGroup(base):
#     """Steps that are shown as ONE row (e.g. the SMT Line). They are still scheduled one after the other."""
#     __tablename__ = "station_group"
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     group_name = Column(String, nullable=False)
#     flow_step_id = Column(Integer, nullable=False)
#     group_type = Column(String, default="LINE")
#     sort_order = Column(Integer, default=0)


# def seed_station_group(db: Session) -> int:
#     """Insert the SMT Line group (steps 10-13) if the table is empty. Returns rows inserted."""
#     if db.query(StationGroup).count():
#         return 0
#     for i, sid in enumerate(SMT_LINE_STEP_IDS):
#         db.add(StationGroup(group_name=SMT_LINE_NAME, flow_step_id=sid, group_type="LINE", sort_order=i))
#     db.commit()
#     return len(SMT_LINE_STEP_IDS)


# # --------------------------------------------------------------------------------------
# # Helpers
# # --------------------------------------------------------------------------------------
# def _iso(dt: datetime) -> str:
#     return dt.replace(microsecond=0).strftime(ISO)


# def _norm(s: Optional[str]) -> str:
#     """Part / PO numbers: ignore spaces and leading zeros."""
#     return (s or "").strip().lstrip("0")


# def _key(s: Optional[str]) -> str:
#     """Name matching: case / punctuation insensitive."""
#     return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# # --------------------------------------------------------------------------------------
# # Calendar with a per-station daily window
# # --------------------------------------------------------------------------------------
# class DayCalendar:
#     """A working day d has a window [d shift_start, +capacity*factor). A station's capacity decides the window length,
#     so a 3-shift station gets a longer window than a 2-shift station. Windows never overlap (capacity <= 24 h)."""

#     def __init__(self, holidays: Dict[date, str], exceptions: Dict[date, str], shift_start: float):
#         self.holidays = holidays
#         self.exceptions = {d: (t or "").strip().lower() for d, t in exceptions.items()}
#         self.shift_start = float(shift_start)

#     def factor(self, d: date) -> float:
#         exc = self.exceptions.get(d)
#         if exc == "working":
#             return 1.0
#         if exc == "half-day":
#             return 0.5
#         if exc == "holiday":
#             return 0.0
#         if d in self.holidays:
#             return 0.0
#         if d.weekday() in WEEKLY_OFF_DAYS:
#             return 0.0
#         if d.weekday() == 5 and ((d.day - 1) // 7 + 1) in ALT_SATURDAYS_OFF:
#             return 0.0
#         return 1.0

#     def off_reason(self, d: date) -> str:
#         if d in self.holidays:
#             return self.holidays[d] or "Holiday"
#         if self.exceptions.get(d) == "holiday":
#             return "Holiday"
#         if d.weekday() == 6:
#             return "Sunday"
#         if d.weekday() == 5:
#             return "1st/3rd Saturday"
#         return "Off"

#     def window(self, d: date, cap_min: float) -> Tuple[datetime, datetime]:
#         ws = datetime.combine(d, time.min) + timedelta(hours=self.shift_start)
#         return ws, ws + timedelta(minutes=cap_min * self.factor(d))

#     def first_working_day(self, d: date) -> date:
#         for _ in range(4000):
#             if self.factor(d) > 0:
#                 return d
#             d += timedelta(days=1)
#         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

#     def locate(self, t: datetime, cap_min: float) -> Tuple[datetime, date]:
#         """Earliest moment >= t inside a working window, and the working day that window belongs to."""
#         d = t.date() - timedelta(days=1)                      # yesterday's window may spill past midnight
#         for _ in range(4000):
#             if self.factor(d) > 0:
#                 ws, we = self.window(d, cap_min)
#                 if t < ws:
#                     return ws, d
#                 if t < we:
#                     return t, d
#             d += timedelta(days=1)
#         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

#     def consume(self, start: datetime, minutes: float, cap_min: float):
#         """Run `minutes` of work from `start`, only inside working windows.
#         Returns (real_start, end, end_day, [(day, minutes_used), ...])."""
#         cur, day = self.locate(start, cap_min)
#         first, rem, usage = cur, float(minutes), []
#         for _ in range(100000):
#             _, we = self.window(day, cap_min)
#             use = min(rem, (we - cur).total_seconds() / 60.0)
#             if use > 0:
#                 usage.append((day, use))
#             rem -= use
#             cur += timedelta(minutes=use)
#             if rem <= 1e-9:
#                 return first, cur, day, usage
#             cur, day = self.locate(we, cap_min)
#         raise PoGanttError(500, "Could not place a run inside the working calendar")


# # --------------------------------------------------------------------------------------
# # Station / PO containers
# # --------------------------------------------------------------------------------------
# class Station:
#     def __init__(self, sid: int, name: str):
#         self.sid, self.name = sid, name
#         self.machines: List[str] = []
#         self.shifts, self.hps, self.cap_min = DEFAULT_SHIFTS, DEFAULT_HOURS_PER_SHIFT, 0.0
#         self.mode, self.batch_size = "SERIES", DEFAULT_BATCH_SIZE
#         self.setup = self.cooldown = 0.0
#         self.cd_working_only = self.next_day_release = False
#         self.operators = 0
#         self.parts: List[str] = []
#         self.role = "MAIN"
#         self.group: Optional[str] = None


# # --------------------------------------------------------------------------------------
# # Builder
# # --------------------------------------------------------------------------------------
# def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
#     """POs come ONLY from PcbData (production_order_tracking is not used).
#     A PO is loadable when EVERY one of its PCBs has status New or Assigned."""
#     q = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt
#                  ).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
#     if plant:
#         q = q.filter(PcbData.plant == plant)
#     by_po: Dict[str, list] = defaultdict(list)
#     for r in q.all():
#         by_po[_norm(r[0])].append(r)

#     cands: Dict[str, Dict[str, Any]] = {}
#     for po, rows in by_po.items():
#         parts = [r[1] for r in rows if r[1]]
#         if not parts:
#             warnings.append(f"PO {po}: PCBs have no part number - ignored")
#             continue
#         part = max(set(parts), key=parts.count)
#         if len(set(parts)) > 1:
#             warnings.append(f"PO {po}: PCBs carry several part numbers ({', '.join(sorted(set(parts)))}) - {part} used")
#         created = [r[4] for r in rows if r[4]]
#         cands[po] = {
#             "po": po, "part": part,
#             "qty": sum(r[2] if (r[2] and r[2] > 0) else 1 for r in rows),          # one row per PCB
#             "created": min(created) if created else None,
#             "started": any((r[3] or "").strip().lower() not in PCB_OPEN_STATUSES for r in rows),
#             "logged": False,
#         }
#     return cands
    

# def step_name(row) -> str:
#     """Stage name of a ProductWorkflowMapping row (via its process_detail relationship -> process_flow_master)."""
#     pd = row.process_detail
#     return (pd.step_name if pd and pd.step_name else None) or f"Step {row.flow_step_id}"


# def build_po_gantt(db: Session, production_orders: Optional[List[str]] = None, plant: Optional[str] = None,
#                    start_date: Optional[date] = None, time_source: str = "actual", label_mode: str = "seq",
#                    show_holidays: bool = False, shift_start: float = DEFAULT_SHIFT_START,
#                    today: Optional[date] = None) -> Dict[str, Any]:
#     if time_source not in ("actual", "sap"):
#         raise PoGanttError(400, "time_source must be 'actual' or 'sap'")
#     if label_mode not in ("seq", "po"):
#         raise PoGanttError(400, "label_mode must be 'seq' or 'po'")
#     warnings: List[str] = []
#     today = today or date.today()

#     # ---------------- calendar ----------------
#     holidays = {h.holiday_date: h.name for h in db.query(PublicHoliday).all()}
#     exceptions = {e.exception_date: e.exception_type for e in db.query(CalendarException).all()}
#     cal = DayCalendar(holidays, exceptions, shift_start)

#     # ---------------- masters (loaded once) ----------------
#     # stages = {s.flow_step_id: s for s in db.query(ProcessFlowMaster).all()}

    
#     is_batch: Dict[int, bool] = defaultdict(bool)
#     for p in db.query(Processtype).all():
#         if p.process_type_batch:
#             is_batch[p.stage_id] = True
#     cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
#     cap_by_key = {_key(c.name): c for c in db.query(StageCapacityDB).all()}
#     products = {p.part_number: p for p in db.query(ProductTypeMaster).all()}
#     part_by_norm = {_norm(pn): pn for pn in products}

#     equipment: Dict[int, List[str]] = defaultdict(list)
#     for e in db.query(Equipments).order_by(Equipments.stage_id, Equipments.id).all():
#         mid = e.machine_id or e.eqpt_no or f"EQ-{e.id}"
#         if e.stage_id is not None and mid not in equipment[e.stage_id]:
#             equipment[e.stage_id].append(mid)

#     shift_names = [s.name for s in db.query(ShiftDefinition).filter(ShiftDefinition.is_active.is_(True))
#                    .order_by(ShiftDefinition.sort_order, ShiftDefinition.id).all()]
#     assigned: Dict[str, set] = defaultdict(set)
#     for a in db.query(OperatorShiftAssignment).all():
#         assigned[a.operator_staff_no].add(a.shift_name)
#     ops_by_stage: Dict[int, List[str]] = defaultdict(list)
#     for o in db.query(OperatorStepMapping).all():
#         who = o.operator_staff_no or o.operator_name
#         if who and who not in ops_by_stage[o.flow_step_id]:
#             ops_by_stage[o.flow_step_id].append(who)

#     def operators_per_shift(sid: int) -> int:
#         ops = ops_by_stage.get(sid, [])
#         if not shift_names:
#             return len(ops)
#         return max((sum(1 for o in ops if not assigned.get(o) or sn in assigned[o]) for sn in shift_names), default=0)

#     # station groups (display only)
#     try:
#         grows = db.query(StationGroup).filter(StationGroup.group_type == "LINE").order_by(
#             StationGroup.group_name, StationGroup.sort_order, StationGroup.id).all()
#     except Exception:                                           # table not created yet
#         db.rollback()
#         grows = []
#     groups: Dict[str, List[int]] = defaultdict(list)
#     for g in grows:
#         groups[g.group_name].append(g.flow_step_id)
#     if not groups:
#         groups[SMT_LINE_NAME] = list(SMT_LINE_STEP_IDS)
#     group_of = {sid: name for name, ids in groups.items() for sid in ids}

#     # child -> main links
#     child_of: Dict[str, str] = {}
#     for main_pn, material in db.query(BOMItem.product_part_number, BOMItem.material).all():
#         c = part_by_norm.get(_norm(material))
#         if c and main_pn and c != main_pn:
#             child_of.setdefault(main_pn, c)
#     for m, c in EXTRA_CHILD_LINKS.items():
#         m, c = part_by_norm.get(_norm(m)), part_by_norm.get(_norm(c))
#         if m and c:
#             child_of[m] = c
#     for m, c in list(child_of.items()):
#         if child_of.get(c) == m:
#             del child_of[m]
#     child_parts = set(child_of.values())

#     # ---------------- select the POs to load ----------------
#     cands = _load_candidates(db, plant, warnings)
#     if production_orders:
#         selected, seen = [], set()
#         for raw in production_orders:
#             k = _norm(raw) or raw
#             if k in seen:
#                 continue
#             seen.add(k)
#             if k not in cands:
#                 raise PoGanttError(404, f"Production order {raw} not found")
#             if cands[k]["started"] or cands[k]["logged"]:
#                 warnings.append(f"PO {k} has already started - scheduled from scratch as requested")
#             selected.append(cands[k])
#         explicit = True
#     else:
#         selected = sorted((c for c in cands.values() if not c["started"] and not c["logged"]),
#                           key=lambda c: (c["created"] or datetime.max, c["po"]))
#         explicit = False

#     # ---------------- routing + times ----------------
#     part_numbers = {c["part"] for c in selected if c["part"]}
#     routing: Dict[str, list] = defaultdict(list)
#     times: Dict[tuple, list] = defaultdict(list)
#     if part_numbers:
#         # for r in db.query(ProductWorkflowMapping).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
#         #         ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
#         #                    ProductWorkflowMapping.id).all():
#         #     routing[r.product_part_number].append(r)
#         for r in db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
#         ).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
#         ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
#                    ProductWorkflowMapping.id).all():
#             routing[r.product_part_number].append(r)

#         for r in db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(part_numbers)).all():
#             times[(r.part_no, r.process_id)].append(r)
#     other = "sap" if time_source == "actual" else "actual"

#     def hours_per_unit(part: str, step) -> Tuple[Optional[float], str]:
#         rows = times.get((part, step.flow_step_id), [])
#         if rows:
#             plant_code = products[part].plant_code if part in products else None
#             row = next((r for r in rows if r.plant == plant_code), rows[0])
#             mt = getattr(row, "machine_time", None)            # column is added later -> getattr
#             if mt and mt > 0:
#                 return float(mt), "machine_time"
#             for src in (time_source, other):
#                 val = row.actual_time if src == "actual" else row.sap_time
#                 if val and val > 0:
#                     return float(val), f"part_process_time.{src}"
#         if step.process_time_seconds and step.process_time_seconds > 0:
#             return step.process_time_seconds / 3600.0, "routing"
#         # stage = stages.get(step.flow_step_id)
#         # cap = cap_by_key.get(_key(stage.step_name)) if stage else None

#         cap = cap_by_key.get(_key(step_name(step)))

#         if cap and cap.manufacturing_time_mins and cap.manufacturing_time_mins > 0:
#             return float(cap.manufacturing_time_mins) / 60.0, "stage_capacity"
#         return None, "none"

#     def capacity_for(names: List[str]) -> Optional[Tuple[int, float]]:
#         for n in names:
#             c = cap_by_key.get(_key(n))
#             if c:
#                 sh = int(c.shifts_per_day or 0)
#                 hp = float(c.hours_per_shift or 0)
#                 return (sh if sh > 0 else DEFAULT_SHIFTS), (hp if hp > 0 else DEFAULT_HOURS_PER_SHIFT)
#         return None

#     # ---------------- build PO objects ----------------
#     pos: List[Dict[str, Any]] = []
#     for c in selected:
#         part, po_no = c["part"], c["po"]
#         steps = routing.get(part or "", [])
#         if not steps or c["qty"] <= 0:
#             msg = (f"PO {po_no}: part {part} has no routing in product_workflow_mapping" if not steps
#                    else f"PO {po_no}: target quantity is 0")
#             if explicit:
#                 raise PoGanttError(422, msg)
#             warnings.append(msg + " - not scheduled")
#             continue
#         pos.append({"po": po_no, "part": part, "qty": c["qty"], "steps": steps, "idx": len(pos) + 1,
#                     "role": "CHILD" if part in child_parts else "MAIN"})
#     if not pos:
#         raise PoGanttError(404, "No production orders to schedule")
#     for p in pos:
#         p["label"] = f"B{p['idx']}" if label_mode == "seq" else p["po"]
#     label_idx = {p["label"]: p["idx"] for p in pos}

#     # ---------------- stations (flow order: child part first, then main) ----------------
#     def depth(part: str) -> int:
#         d = 0
#         while part in child_of and d < 10:
#             part, d = child_of[part], d + 1
#         return d

#     scheduled_parts = {p["part"] for p in pos}
#     tops = sorted(pt for pt in scheduled_parts | set(child_of) if pt not in child_parts)
#     part_order: List[str] = []
#     for top in tops:
#         chain, pt = [], top
#         while pt and pt not in chain:
#             chain.append(pt)
#             pt = child_of.get(pt)
#         for pt in reversed(chain):
#             if pt in scheduled_parts and pt not in part_order:
#                 part_order.append(pt)
#     part_order += sorted(pt for pt in scheduled_parts if pt not in part_order)

#     stations: Dict[int, Station] = {}
#     flow_order: List[int] = []
#     for part in part_order:
#         for st_row in routing.get(part, []):
#             sid = st_row.flow_step_id
#             if sid not in stations:
#                 # stage = stages.get(sid)

#                 s = Station(sid, step_name(st_row))
#                 # s = Station(sid, stage.step_name if stage else f"Step {sid}")
#                 s.group = group_of.get(sid)
#                 s.mode = "BATCH" if is_batch.get(sid) else "SERIES"
#                 c = cfg.get(sid)
#                 if c:
#                     s.batch_size = max(int(c.batch_size or DEFAULT_BATCH_SIZE), 1)
#                     s.setup = float(c.setup_minutes or 0)
#                     s.cooldown = float(c.cooldown_minutes or 0)
#                     s.cd_working_only = bool(c.cooldown_working_time_only)
#                     s.next_day_release = bool(c.next_day_release) and s.mode == "BATCH"
#                 names = ([s.group] if s.group else []) + [s.name]
#                 got = capacity_for(names)
#                 if got:
#                     s.shifts, s.hps = got
#                 s.cap_min = min(s.shifts * s.hps * 60.0, 1440.0)
#                 s.machines = list(equipment.get(sid, [])) or [f"MANUAL-{sid}"]
#                 s.operators = operators_per_shift(sid)
#                 s.role = "CHILD" if part in child_parts else "MAIN"
#                 stations[sid] = s
#                 flow_order.append(sid)
#             if part not in stations[sid].parts:
#                 stations[sid].parts.append(part)

#     # ---------------- child PO -> main PO supply (FIFO by quantity) ----------------
#     depends_on: Dict[str, List[str]] = defaultdict(list)
#     by_part: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     for p in pos:
#         by_part[p["part"]].append(p)
#     for main_pn, child_pn in child_of.items():
#         mains, childs = by_part.get(main_pn, []), by_part.get(child_pn, [])
#         if not mains:
#             continue
#         if not childs:
#             warnings.append(f"Part {main_pn}: no child PO ({child_pn}) loaded - child PCBs assumed in stock, "
#                             f"main PO(s) {', '.join(m['label'] for m in mains)} start right away")
#             continue
#         supply, run = [], 0
#         for c in childs:
#             supply.append((run, run + c["qty"], c["po"]))
#             run += c["qty"]
#         need = 0
#         for m in mains:
#             lo, hi = need, need + m["qty"]
#             need = hi
#             depends_on[m["po"]] = [cpo for (a, b, cpo) in supply if a < hi and b > lo]
#             if hi > run:
#                 warnings.append(f"PO {m['po']}: needs more child PCBs than the loaded child POs provide - rest assumed in stock")

#     # ---------------- schedule (finite capacity) ----------------
#     start_day = cal.first_working_day(start_date or today)
#     start_dt = datetime.combine(start_day, time.min) + timedelta(hours=shift_start)
#     default_cap = min(DEFAULT_SHIFTS * DEFAULT_HOURS_PER_SHIFT * 60.0, 1440.0)

#     free_at: Dict[Tuple[int, str], datetime] = defaultdict(lambda: datetime.min)
#     usage: Dict[int, Dict[date, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
#     runs: Dict[Tuple[int, str], List[datetime]] = {}
#     po_ready: Dict[str, datetime] = {}
#     po_span: Dict[str, List[datetime]] = {}
#     missing_time: Dict[str, List[str]] = defaultdict(list)

#     for p in sorted(pos, key=lambda x: (depth(x["part"]), x["idx"])):
#         prev_ready = max([start_dt] + [po_ready[c] for c in depends_on.get(p["po"], []) if c in po_ready])
#         for step in p["steps"]:
#             st = stations[step.flow_step_id]
#             hrs, _src = hours_per_unit(p["part"], step)
#             if hrs is None:
#                 missing_time[p["part"]].append(st.name)
#                 minutes = FALLBACK_MINUTES
#             elif st.mode == "BATCH":
#                 minutes = math.ceil(p["qty"] / st.batch_size) * hrs * 60.0
#             else:
#                 minutes = p["qty"] * hrs * 60.0
#             minutes = max(minutes + st.setup, 1.0)

#             best = None
#             for mid in st.machines:
#                 s0 = max(prev_ready, free_at[(st.sid, mid)])
#                 s, e, eday, use = cal.consume(s0, minutes, st.cap_min)
#                 if best is None or e < best[2]:
#                     best = (mid, s, e, eday, use)
#             mid, s, e, eday, use = best
#             free_at[(st.sid, mid)] = e
#             for d, mins in use:
#                 usage[st.sid][d][p["label"]] += mins
#             span = runs.setdefault((st.sid, p["label"]), [s, e])
#             span[0], span[1] = min(span[0], s), max(span[1], e)
#             ps = po_span.setdefault(p["po"], [s, e])
#             ps[0], ps[1] = min(ps[0], s), max(ps[1], e)

#             ready = e                                            # when the PO may enter the next station
#             if st.next_day_release:
#                 ready = datetime.combine(cal.first_working_day(eday + timedelta(days=1)), time.min) + timedelta(hours=shift_start)
#             if st.cooldown > 0:
#                 if st.cd_working_only:
#                     ready = cal.consume(ready, st.cooldown, default_cap)[1]
#                 else:
#                     ready = ready + timedelta(minutes=st.cooldown)
#             prev_ready = ready
#         po_ready[p["po"]] = prev_ready

#     for part, names in missing_time.items():
#         uniq = list(dict.fromkeys(names))
#         warnings.append(f"Part {part}: no process time for {len(uniq)} step(s) "
#                         f"[{', '.join(uniq[:6])}{'...' if len(uniq) > 6 else ''}] - {FALLBACK_MINUTES:g} min used")

#     # ---------------- days ----------------
#     used_days = [d for per_day in usage.values() for d in per_day]
#     last_day = max(used_days + [start_day])
#     days, day_no, working_nos = [], {}, 0
#     d = start_day
#     while d <= last_day:
#         if cal.factor(d) > 0:
#             working_nos += 1
#             day_no[d] = working_nos
#             days.append({"working_day_no": working_nos, "date": d.isoformat(), "weekday": d.strftime("%a"),
#                          "is_holiday": False, "off_reason": None})
#         elif show_holidays:
#             days.append({"working_day_no": None, "date": d.isoformat(), "weekday": d.strftime("%a"),
#                          "is_holiday": True, "off_reason": cal.off_reason(d)})
#         d += timedelta(days=1)

#     # ---------------- rows ----------------
#     def order_labels(labels) -> List[str]:
#         return sorted(labels, key=lambda x: label_idx.get(x, 0))

#     def cells_for(sids: List[int]) -> List[Dict[str, Any]]:
#         out = []
#         for dd, no in day_no.items():
#             labels, used, capacity = set(), 0.0, 0.0
#             for sid in sids:
#                 s = stations[sid]
#                 capacity += len(s.machines) * s.cap_min * cal.factor(dd)
#                 u = usage.get(sid, {}).get(dd)
#                 if u:
#                     used += sum(u.values())
#                     labels.update(u)
#             if labels:
#                 out.append({"working_day_no": no, "date": dd.isoformat(), "pos": order_labels(labels),
#                             "color": ORANGE if len(labels) >= 2 else BLUE,
#                             "minutes_used": round(used, 1), "capacity_minutes": round(capacity, 1)})
#         return out

#     def runs_for(sids: List[int]) -> List[Dict[str, str]]:
#         merged: Dict[str, List[datetime]] = {}
#         for (sid, label), (s, e) in runs.items():
#             if sid in sids:
#                 cur = merged.setdefault(label, [s, e])
#                 cur[0], cur[1] = min(cur[0], s), max(cur[1], e)
#         return [{"label": lb, "start": _iso(v[0]), "end": _iso(v[1])}
#                 for lb, v in sorted(merged.items(), key=lambda kv: (kv[1][0], label_idx.get(kv[0], 0)))]

#     rows: List[Dict[str, Any]] = []
#     done_groups = set()
#     for sid in flow_order:
#         s = stations[sid]
#         if s.group and s.group in done_groups:
#             continue
#         if not s.group:
#             rows.append({"station_id": f"STEP-{sid}", "name": s.name, "flow_step_id": sid,
#                          "part_number": s.parts[0], "part_numbers": s.parts, "role": s.role,
#                          "shifts": s.shifts, "mins_per_shift": int(s.hps * 60), "machines": len(s.machines),
#                          "operators_per_shift": s.operators, "process_mode": s.mode,
#                          "cells": cells_for([sid]), "po_runs": runs_for([sid])})
#             continue
#         done_groups.add(s.group)
#         members = [stations[m] for m in flow_order if stations[m].group == s.group]
#         gcap = capacity_for([s.group])
#         lead = max(members, key=lambda m: m.shifts)
#         shifts, hps = gcap if gcap else (lead.shifts, lead.hps)
#         mids = [m.sid for m in members]
#         rows.append({"station_id": f"GROUP-{s.group}", "name": s.group, "part_number": members[0].parts[0],
#                      "part_numbers": sorted({pt for m in members for pt in m.parts}), "role": members[0].role,
#                      "shifts": shifts, "mins_per_shift": int(hps * 60),
#                      "machines": max(len(m.machines) for m in members),
#                      "operators_per_shift": max(m.operators for m in members), "process_mode": "LINE",
#                      "cells": cells_for(mids), "po_runs": runs_for(mids),
#                      "members": [{"step_name": m.name, "flow_step_id": m.sid, "shifts": m.shifts,
#                                   "machines": len(m.machines), "process_mode": m.mode,
#                                   "cells": cells_for([m.sid]), "po_runs": runs_for([m.sid])} for m in members]})

#     assumptions = [
#         "Unit of work is the whole PO (target quantity); POs move through the stations as a block.",
#         f"Shifts per station come from stage_capacity (default {DEFAULT_SHIFTS} x {DEFAULT_HOURS_PER_SHIFT:g} h); the day starts at {_hm(shift_start)}.",
#         "Off days: Sundays, 1st and 3rd Saturdays, public holidays and calendar 'Holiday' exceptions; 'Working' reopens a day, 'Half-Day' halves it.",
#         f"Time per unit = machine time if present, else {'actual' if time_source == 'actual' else 'SAP'} man time (fallback to the other, routing, stage_capacity).",
#         "SMT Line steps are scheduled one after the other and only shown as one row.",
#         "Operators per shift is informational; it does not limit the schedule.",
#     ]
#     return {
#         "meta": {
#             "number_of_pos": len(pos), "start_date": start_day.isoformat(), "finish_date": last_day.isoformat(),
#             "working_days": working_nos, "time_source": time_source, "label_mode": label_mode,
#             "pos": [{"label": p["label"], "production_order": p["po"], "part_number": p["part"], "role": p["role"],
#                      "quantity": p["qty"], "depends_on": depends_on.get(p["po"], []),
#                      "start": _iso(po_span[p["po"]][0]), "end": _iso(po_span[p["po"]][1])} for p in pos],
#         },
#         "days": days, "stations": rows, "warnings": warnings, "assumptions": assumptions,
#     }


# def _hm(h: float) -> str:
#     hh = int(h)
#     return f"{hh:02d}:{int(round((h - hh) * 60)):02d}"


# # --------------------------------------------------------------------------------------
# # Excel export
# # --------------------------------------------------------------------------------------
# def build_po_gantt_xlsx(result: Dict[str, Any]) -> bytes:
#     from openpyxl import Workbook
#     from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
#     from openpyxl.utils import get_column_letter

#     font = lambda **kw: Font(name="Arial", size=10, **kw)
#     thin = Side(style="thin", color="BFBFBF")
#     border = Border(left=thin, right=thin, top=thin, bottom=thin)
#     head = PatternFill("solid", start_color="DDE3EE")
#     off = PatternFill("solid", start_color="D9D9D9")
#     fills = {BLUE: PatternFill("solid", start_color="9FC5E8"), ORANGE: PatternFill("solid", start_color="F6B26B")}
#     center = Alignment(horizontal="center", vertical="center", wrap_text=True)

#     wb = Workbook()
#     ws = wb.active
#     ws.title = "PO on Station"
#     days = result["days"]
#     ws.column_dimensions["A"].width = 30
#     ws.column_dimensions["B"].width = 10
#     for i, label in enumerate(("Working day #", "Date", "Day"), start=1):
#         c = ws.cell(row=i, column=1, value=label)
#         c.font, c.fill, c.border = font(bold=True), head, border
#         ws.cell(row=i, column=2).fill = head
#         ws.cell(row=i, column=2).border = border
#     for j, d in enumerate(days, start=3):
#         ws.column_dimensions[get_column_letter(j)].width = 11
#         dt = date.fromisoformat(d["date"])
#         vals = ("Off" if d["is_holiday"] else d["working_day_no"], dt.strftime("%d-%b"), d["weekday"])
#         for i, v in enumerate(vals, start=1):
#             c = ws.cell(row=i, column=j, value=v)
#             c.font, c.border, c.alignment = font(bold=(i == 1)), border, center
#             c.fill = off if d["is_holiday"] else head
#     col_of = {d["working_day_no"]: j for j, d in enumerate(days, start=3) if d["working_day_no"]}
#     for r, st in enumerate(result["stations"], start=4):
#         a = ws.cell(row=r, column=1, value=st["name"])
#         a.font, a.border = font(bold=True), border
#         b = ws.cell(row=r, column=2, value=f"{st['shifts']} shift")
#         b.font, b.border, b.alignment = font(), border, center
#         for j, d in enumerate(days, start=3):
#             c = ws.cell(row=r, column=j)
#             c.border = border
#             if d["is_holiday"]:
#                 c.fill = off
#         for cell in st["cells"]:
#             c = ws.cell(row=r, column=col_of[cell["working_day_no"]], value=" ".join(cell["pos"]))
#             c.fill, c.font, c.alignment = fills[cell["color"]], font(bold=True), center
#     r = 4 + len(result["stations"]) + 1
#     ws.cell(row=r, column=1, value="Legend").font = font(bold=True)
#     for k, (lab, txt, col) in enumerate((("Blue", "1 PO on the station", BLUE), ("Orange", "2 or more POs share the station", ORANGE)), 1):
#         ws.cell(row=r + k, column=1, value=f"{lab}: {txt}").font = font()
#         ws.cell(row=r + k, column=2).fill = fills[col]
#     r += 4
#     for j, h in enumerate(("Label", "Production order", "Part number", "Role", "Quantity", "Start", "End"), start=1):
#         c = ws.cell(row=r, column=j, value=h)
#         c.font, c.fill, c.border = font(bold=True), head, border
#     for k, p in enumerate(result["meta"]["pos"], start=1):
#         for j, v in enumerate((p["label"], p["production_order"], p["part_number"], p["role"], p["quantity"],
#                                p["start"], p["end"]), start=1):
#             c = ws.cell(row=r + k, column=j, value=v)
#             c.font, c.border = font(), border
#     ws.freeze_panes = "C4"
#     buf = io.BytesIO()
#     wb.save(buf)
#     return buf.getvalue()


# # --------------------------------------------------------------------------------------
# # Router
# # --------------------------------------------------------------------------------------
# def create_po_gantt_router(init_db, verify_token=None, engine=None) -> APIRouter:
#     """engine (optional): creates the station_group table if missing and seeds the SMT Line group."""
#     router = APIRouter()
#     deps = [Depends(verify_token)] if verify_token else []
#     if engine is not None:
#         StationGroup.__table__.create(bind=engine, checkfirst=True)
#         from sqlalchemy.orm import sessionmaker
#         with sessionmaker(bind=engine)() as s:
#             seed_station_group(s)

#     def _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start):
#         try:
#             return build_po_gantt(db, production_order, plant, start_date, time_source, label_mode,
#                                   show_holidays, shift_start)
#         except PoGanttError as e:
#             raise HTTPException(status_code=e.status_code, detail=e.detail)

#     @router.get("/schedule/po-gantt", dependencies=deps)
#     def po_gantt(
#         production_order: Optional[List[str]] = Query(None, description="PO numbers to load; order = load priority"),
#         plant: Optional[str] = Query(None),
#         start_date: Optional[date] = Query(None, description="default: first working day on/after today"),
#         time_source: str = Query("actual"),
#         label_mode: str = Query("seq", description="'seq' = B1, B2... | 'po' = PO number"),
#         show_holidays: bool = Query(False, description="show off days as empty flagged columns"),
#         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=10),
#         db: Session = Depends(init_db),
#     ):
#         return _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)

#     @router.get("/schedule/po-gantt/export", dependencies=deps)
#     def po_gantt_export(
#         production_order: Optional[List[str]] = Query(None),
#         plant: Optional[str] = Query(None),
#         start_date: Optional[date] = Query(None),
#         time_source: str = Query("actual"),
#         label_mode: str = Query("seq"),
#         show_holidays: bool = Query(False),
#         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=10),
#         db: Session = Depends(init_db),
#     ):
#         result = _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)
#         return StreamingResponse(
#             io.BytesIO(build_po_gantt_xlsx(result)),
#             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#             headers={"Content-Disposition": 'attachment; filename="po_gantt.xlsx"'},
#         )

#     return router




















"""
po_gantt_service.py  -  "PO on Station" Gantt

    GET /schedule/po-gantt            the schedule as JSON (rows = stations, bars = PO runs)
    GET /schedule/po-gantt/orders     yet-to-start POs, for the PO picker
    GET /schedule/po-gantt/export     the same schedule as .xlsx

Hook-up (Data_Server.py) - unchanged:
    from po_gantt_service import create_po_gantt_router
    app.include_router(create_po_gantt_router(init_db, verify_token))

RULES
 * POs come ONLY from PcbData. A PO is open when every one of its PCBs is New / Assigned; quantity = sum of PCB quantity.
 * CHILD / MAIN comes from product_type_master.sub_product_type_name. A MAIN part is fed by the CHILD part with the
   same product_type_name (HEXA child 62005774DA -> HEXA main 113300033357). bom_items is only a fallback link.
 * The flow of a part = product_workflow_mapping ordered by step_sequence. A PO runs its flow station after station,
   as one block (the whole quantity). Different POs overlap freely on different stations.
 * Child POs are scheduled first. A main PO's first station waits for the child PO(s) that feed it (FIFO by quantity).
 * SMT LINE = the 4 TOP SIDE steps in LINE_GROUPS. They are ONE station / ONE row and are never shown on their own.
   A PO runs them in one go INSIDE ONE WORKING DAY: if the run does not fit in what is left of the day it starts at
   the next working day. Line time = slowest step for the whole PO + one board through each of the other steps.
 * Rows: CHILD PROCESSES first (child flow order), then MAIN PROCESSES (main flow order). A station used by both
   shows in both sections with its own POs; the machine capacity is shared.
 * Time per unit = part_process_time.machine_time (if the column exists and > 0) else actual_time / sap_time (hours);
   fallbacks: routing process_time_seconds, stage_capacity.manufacturing_time_mins, then 1 min + warning.
   SERIES: qty * t.  BATCH: ceil(qty / batch_size) * t.  Plus setup_minutes once per PO run.
 * Shifts per station from stage_capacity (by name; for the line the line name first); default 2 x 7 h.
   The working window of a day starts at shift_start (06:00) and lasts shifts * hours.
 * Off days: Sundays, 1st/3rd Saturdays, public_holidays, calendar_exceptions 'Holiday';
   'Working' reopens a day, 'Half-Day' halves its window.
 * The old station_group table is no longer used (it can be dropped).
"""
import io
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from Database_models import (
    BOMItem, CalendarException, Equipments, OperatorShiftAssignment, OperatorStepMapping, PartProcessTime, PcbData,
    Processtype, ProductTypeMaster, ProductWorkflowMapping, PublicHoliday, ShiftDefinition, StageCapacityDB,
    StageScheduleConfig,
)

# --------------------------------------------------------------------------------------
# Constants (change the rules in one place)
# --------------------------------------------------------------------------------------
ISO = "%Y-%m-%dT%H:%M:%S"
WEEKLY_OFF_DAYS = (6,)             # Python weekday(): Monday = 0 ... Sunday = 6
ALT_SATURDAYS_OFF = (1, 3)         # 1st and 3rd Saturday of the month
DEFAULT_SHIFTS = 2
DEFAULT_HOURS_PER_SHIFT = 7.0
DEFAULT_SHIFT_START = 6.0          # day window starts 06:00
DEFAULT_BATCH_SIZE = 30
FALLBACK_MINUTES = 1.0
PCB_OPEN_STATUSES = {"new", "assigned"}      # PcbData.status values that count as "not started"
EXTRA_CHILD_LINKS: Dict[str, str] = {}      # {main_part_no: child_part_no} to force a link

ROLES = ("CHILD", "MAIN")                   # section order of the rows

# Steps that run as ONE line, inside one working day, shown as ONE row (matched by step name, case-insensitive)
LINE_GROUPS: Dict[str, Tuple[str, ...]] = {
    "SMT LINE": (
        "SOLDER PASTE PRINTING - TOP SIDE",
        "SOLDER PASTE INSPECTION - TOP SIDE",
        "PICK N PLACE - TOP SIDE",
        "REFLOW - TOP SIDE",
    ),
}

BLUE, ORANGE = "BLUE", "ORANGE"


class PoGanttError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime(ISO)


def _norm(s: Optional[str]) -> str:
    """Part / PO numbers: ignore spaces and leading zeros."""
    return (s or "").strip().lstrip("0")


def _key(s: Optional[str]) -> str:
    """Name matching: case / punctuation insensitive."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _hm(h: float) -> str:
    hh = int(h)
    return f"{hh:02d}:{int(round((h - hh) * 60)):02d}"


def step_name(row) -> str:
    """Stage name of a ProductWorkflowMapping row (via its process_detail relationship -> process_flow_master)."""
    pd = row.process_detail
    return (pd.step_name if pd and pd.step_name else None) or f"Step {row.flow_step_id}"


# --------------------------------------------------------------------------------------
# Calendar with a per-station daily window
# --------------------------------------------------------------------------------------
class DayCalendar:
    """A working day d has a window [d shift_start, +capacity*factor). A station's capacity decides the window length,
    so a 3-shift station gets a longer window than a 2-shift station. Windows never overlap (capacity <= 24 h)."""

    def __init__(self, holidays: Dict[date, str], exceptions: Dict[date, str], shift_start: float):
        self.holidays = holidays
        self.exceptions = {d: (t or "").strip().lower() for d, t in exceptions.items()}
        self.shift_start = float(shift_start)

    def factor(self, d: date) -> float:
        exc = self.exceptions.get(d)
        if exc == "working":
            return 1.0
        if exc == "half-day":
            return 0.5
        if exc == "holiday":
            return 0.0
        if d in self.holidays:
            return 0.0
        if d.weekday() in WEEKLY_OFF_DAYS:
            return 0.0
        if d.weekday() == 5 and ((d.day - 1) // 7 + 1) in ALT_SATURDAYS_OFF:
            return 0.0
        return 1.0

    def off_reason(self, d: date) -> str:
        if d in self.holidays:
            return self.holidays[d] or "Holiday"
        if self.exceptions.get(d) == "holiday":
            return "Holiday"
        if d.weekday() == 6:
            return "Sunday"
        if d.weekday() == 5:
            return "1st/3rd Saturday"
        return "Off"

    def window(self, d: date, cap_min: float) -> Tuple[datetime, datetime]:
        ws = datetime.combine(d, time.min) + timedelta(hours=self.shift_start)
        return ws, ws + timedelta(minutes=cap_min * self.factor(d))

    def first_working_day(self, d: date) -> date:
        for _ in range(4000):
            if self.factor(d) > 0:
                return d
            d += timedelta(days=1)
        raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

    def locate(self, t: datetime, cap_min: float) -> Tuple[datetime, date]:
        """Earliest moment >= t inside a working window, and the working day that window belongs to."""
        d = t.date() - timedelta(days=1)                      # yesterday's window may spill past midnight
        for _ in range(4000):
            if self.factor(d) > 0:
                ws, we = self.window(d, cap_min)
                if t < ws:
                    return ws, d
                if t < we:
                    return t, d
            d += timedelta(days=1)
        raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

    def consume(self, start: datetime, minutes: float, cap_min: float):
        """Run `minutes` of work from `start`, only inside working windows.
        Returns (real_start, end, end_day, [(day, seg_start, seg_end, minutes), ...])."""
        cur, day = self.locate(start, cap_min)
        first, rem, segs = cur, float(minutes), []
        for _ in range(100000):
            _, we = self.window(day, cap_min)
            use = min(rem, (we - cur).total_seconds() / 60.0)
            if use > 1e-9:
                segs.append((day, cur, cur + timedelta(minutes=use), use))
            rem -= use
            cur += timedelta(minutes=use)
            if rem <= 1e-9:
                return first, cur, day, segs
            cur, day = self.locate(we, cap_min)
        raise PoGanttError(500, "Could not place a run inside the working calendar")

    def place_within_day(self, start: datetime, minutes: float, cap_min: float):
        """Like consume, but the whole run must finish inside ONE working day. If it does not fit in what is left of
        the day, it starts at the next working day that can hold it. A run longer than a full day has to spill over.
        Returns consume(...) + (fits_in_one_day,)."""
        t = start
        for _ in range(4000):
            cur, day = self.locate(t, cap_min)
            _, we = self.window(day, cap_min)
            if minutes <= (we - cur).total_seconds() / 60.0 + 1e-9:
                return self.consume(cur, minutes, cap_min) + (True,)
            if minutes > cap_min + 1e-9:                      # longer than any full day
                return self.consume(cur, minutes, cap_min) + (False,)
            t = we                                             # not enough left today -> next working day
        raise PoGanttError(500, "Could not place a line run inside one working day")


# --------------------------------------------------------------------------------------
# Station container
# --------------------------------------------------------------------------------------
class Station:
    def __init__(self, key: str, name: str, kind: str, step_ids: List[int]):
        self.key, self.name, self.kind, self.step_ids = key, name, kind, list(step_ids)   # kind: STEP | LINE
        self.steps: List[str] = []                       # member step names (LINE only)
        self.machines: List[str] = []
        self.shifts, self.hps, self.cap_min = DEFAULT_SHIFTS, DEFAULT_HOURS_PER_SHIFT, 0.0
        self.mode, self.batch_size = "SERIES", DEFAULT_BATCH_SIZE
        self.setup = self.cooldown = 0.0
        self.cd_working_only = self.next_day_release = False
        self.operators = 0


# --------------------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------------------
def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
    """POs come ONLY from PcbData (production_order_tracking is not used).
    A PO is loadable when EVERY one of its PCBs has status New or Assigned."""
    q = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt
                 ).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
    if plant:
        q = q.filter(PcbData.plant == plant)
    by_po: Dict[str, list] = defaultdict(list)
    for r in q.all():
        by_po[_norm(r[0])].append(r)

    cands: Dict[str, Dict[str, Any]] = {}
    for po, rows in by_po.items():
        parts = [r[1] for r in rows if r[1]]
        if not parts:
            warnings.append(f"PO {po}: PCBs have no part number - ignored")
            continue
        part = max(set(parts), key=parts.count)
        if len(set(parts)) > 1:
            warnings.append(f"PO {po}: PCBs carry several part numbers ({', '.join(sorted(set(parts)))}) - {part} used")
        created = [r[4] for r in rows if r[4]]
        cands[po] = {
            "po": po, "part": part,
            "qty": sum(r[2] if (r[2] and r[2] > 0) else 1 for r in rows),          # one row per PCB
            "created": min(created) if created else None,
            "started": any((r[3] or "").strip().lower() not in PCB_OPEN_STATUSES for r in rows),
        }
    return cands


def _product_links(db: Session, warnings: Optional[List[str]] = None):
    """Returns (products, child_of {main_pn: child_pn}, role_of(pn) -> 'CHILD' | 'MAIN').
    1. product_type_master: CHILD and MAIN rows with the same product_type_name (and plant) belong together.
    2. bom_items fallback: the child P/N appears as a material of the main P/N (leading zeros ignored).
    3. EXTRA_CHILD_LINKS override."""
    products = {p.part_number: p for p in db.query(ProductTypeMaster).all()}
    part_by_norm = {_norm(pn): pn for pn in products}

    def sub(pn: str) -> str:
        p = products.get(pn)
        return (p.sub_product_type_name or "").strip().upper() if p else ""

    child_of: Dict[str, str] = {}
    families: Dict[tuple, Dict[str, List[str]]] = defaultdict(lambda: {"CHILD": [], "MAIN": []})
    for pn, p in products.items():
        s = sub(pn)
        if s in ROLES and _key(p.product_type_name):
            families[(_key(p.product_type_name), p.plant_code)][s].append(pn)
    for (fam, _plant), g in sorted(families.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        childs = sorted(g["CHILD"])
        for m in g["MAIN"]:
            if childs:
                child_of[m] = childs[0]
                if len(childs) > 1 and warnings is not None:
                    warnings.append(f"Family {fam.upper()}: several child parts ({', '.join(childs)}) - "
                                    f"{childs[0]} used to feed {m}")

    for main_pn, material in db.query(BOMItem.product_part_number, BOMItem.material).all():
        m = part_by_norm.get(_norm(main_pn)) or main_pn
        c = part_by_norm.get(_norm(material))
        if c and m and c != m and m not in child_of and sub(m) != "CHILD" and sub(c) != "MAIN":
            child_of[m] = c
    for m, c in EXTRA_CHILD_LINKS.items():
        m, c = part_by_norm.get(_norm(m)), part_by_norm.get(_norm(c))
        if m and c:
            child_of[m] = c
    for m, c in list(child_of.items()):
        if child_of.get(c) == m:
            del child_of[m]
    child_parts = set(child_of.values())

    def role_of(pn: Optional[str]) -> str:
        s = sub(pn or "")
        if s in ROLES:
            return s
        return "CHILD" if pn in child_parts else "MAIN"

    return products, child_of, role_of


def list_open_orders(db: Session, plant: Optional[str] = None) -> Dict[str, Any]:
    """Yet-to-start POs for the picker (oldest first)."""
    warnings: List[str] = []
    _, _, role_of = _product_links(db)
    cands = _load_candidates(db, plant, warnings)
    open_pos = sorted((c for c in cands.values() if not c["started"]),
                      key=lambda c: (c["created"] or datetime.max, c["po"]))
    return {"orders": [{"production_order": c["po"], "part_number": c["part"], "quantity": c["qty"],
                        "role": role_of(c["part"]), "created": c["created"].isoformat() if c["created"] else None}
                       for c in open_pos],
            "warnings": warnings}


# --------------------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------------------
def build_po_gantt(db: Session, production_orders: Optional[List[str]] = None, plant: Optional[str] = None,
                   start_date: Optional[date] = None, time_source: str = "actual", label_mode: str = "seq",
                   show_holidays: bool = False, shift_start: float = DEFAULT_SHIFT_START,
                   today: Optional[date] = None) -> Dict[str, Any]:
    if time_source not in ("actual", "sap"):
        raise PoGanttError(400, "time_source must be 'actual' or 'sap'")
    if label_mode not in ("seq", "po"):
        raise PoGanttError(400, "label_mode must be 'seq' or 'po'")
    warnings: List[str] = []
    today = today or date.today()

    # ---------------- calendar ----------------
    holidays = {h.holiday_date: h.name for h in db.query(PublicHoliday).all()}
    exceptions = {e.exception_date: e.exception_type for e in db.query(CalendarException).all()}
    cal = DayCalendar(holidays, exceptions, shift_start)

    # ---------------- masters (loaded once) ----------------
    products, child_of, role_of = _product_links(db, warnings)

    is_batch: Dict[int, bool] = defaultdict(bool)
    for p in db.query(Processtype).all():
        if p.process_type_batch:
            is_batch[p.stage_id] = True
    cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
    cap_by_key = {_key(c.name): c for c in db.query(StageCapacityDB).all()}

    equipment: Dict[int, List[str]] = defaultdict(list)
    for e in db.query(Equipments).order_by(Equipments.stage_id, Equipments.id).all():
        mid = e.machine_id or e.eqpt_no or f"EQ-{e.id}"
        if e.stage_id is not None and mid not in equipment[e.stage_id]:
            equipment[e.stage_id].append(mid)

    shift_names = [s.name for s in db.query(ShiftDefinition).filter(ShiftDefinition.is_active.is_(True))
                   .order_by(ShiftDefinition.sort_order, ShiftDefinition.id).all()]
    assigned: Dict[str, set] = defaultdict(set)
    for a in db.query(OperatorShiftAssignment).all():
        assigned[a.operator_staff_no].add(a.shift_name)
    ops_by_stage: Dict[int, List[str]] = defaultdict(list)
    for o in db.query(OperatorStepMapping).all():
        who = o.operator_staff_no or o.operator_name
        if who and who not in ops_by_stage[o.flow_step_id]:
            ops_by_stage[o.flow_step_id].append(who)

    def operators_per_shift(sid: int) -> int:
        ops = ops_by_stage.get(sid, [])
        if not shift_names:
            return len(ops)
        return max((sum(1 for o in ops if not assigned.get(o) or sn in assigned[o]) for sn in shift_names), default=0)

    line_of_name = {_key(n): g for g, names in LINE_GROUPS.items() for n in names}

    # ---------------- select the POs to load ----------------
    cands = _load_candidates(db, plant, warnings)
    if production_orders:
        selected, seen = [], set()
        for raw in production_orders:
            k = _norm(raw) or raw
            if k in seen:
                continue
            seen.add(k)
            if k not in cands:
                raise PoGanttError(404, f"Production order {raw} not found")
            if cands[k]["started"]:
                warnings.append(f"PO {k} has already started - scheduled from scratch as requested")
            selected.append(cands[k])
        explicit = True
    else:
        selected = sorted((c for c in cands.values() if not c["started"]),
                          key=lambda c: (c["created"] or datetime.max, c["po"]))
        explicit = False

    # ---------------- routing (product_workflow_mapping) + times ----------------
    part_numbers = {c["part"] for c in selected if c["part"]}
    routing: Dict[str, list] = defaultdict(list)
    times: Dict[tuple, list] = defaultdict(list)
    if part_numbers:
        for r in db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
                ).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
                ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
                           ProductWorkflowMapping.id).all():
            routing[r.product_part_number].append(r)
        for r in db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(part_numbers)).all():
            times[(r.part_no, r.process_id)].append(r)
    other = "sap" if time_source == "actual" else "actual"

    def hours_per_unit(part: str, step) -> Tuple[Optional[float], str]:
        rows = times.get((part, step.flow_step_id), [])
        if rows:
            plant_code = products[part].plant_code if part in products else None
            row = next((r for r in rows if r.plant == plant_code), rows[0])
            mt = getattr(row, "machine_time", None)            # column is added later -> getattr
            if mt and mt > 0:
                return float(mt), "machine_time"
            for src in (time_source, other):
                val = row.actual_time if src == "actual" else row.sap_time
                if val and val > 0:
                    return float(val), f"part_process_time.{src}"
        if getattr(step, "process_time_seconds", None) and step.process_time_seconds > 0:
            return step.process_time_seconds / 3600.0, "routing"
        cap = cap_by_key.get(_key(step_name(step)))
        if cap and cap.manufacturing_time_mins and cap.manufacturing_time_mins > 0:
            return float(cap.manufacturing_time_mins) / 60.0, "stage_capacity"
        return None, "none"

    def capacity_for(names: List[str]) -> Optional[Tuple[int, float]]:
        for n in names:
            c = cap_by_key.get(_key(n))
            if c:
                sh = int(c.shifts_per_day or 0)
                hp = float(c.hours_per_shift or 0)
                return (sh if sh > 0 else DEFAULT_SHIFTS), (hp if hp > 0 else DEFAULT_HOURS_PER_SHIFT)
        return None

    # ---------------- operations of a part (its flow, with the line steps merged) ----------------
    ops_cache: Dict[str, List[Dict[str, Any]]] = {}

    def ops_for(part: str) -> List[Dict[str, Any]]:
        if part in ops_cache:
            return ops_cache[part]
        steps = routing.get(part, [])
        ops, done = [], set()
        for st in steps:
            g = line_of_name.get(_key(step_name(st)))
            if g:
                if g in done:
                    continue
                done.add(g)
                members = [x for x in steps if line_of_name.get(_key(step_name(x))) == g]
                ops.append({"key": f"LINE-{g}", "line": g, "steps": members})
            else:
                ops.append({"key": f"STEP-{st.flow_step_id}", "line": None, "steps": [st]})
        ops_cache[part] = ops
        return ops

    # ---------------- build PO objects ----------------
    pos: List[Dict[str, Any]] = []
    for c in selected:
        part, po_no = c["part"], c["po"]
        steps = routing.get(part or "", [])
        if not steps or c["qty"] <= 0:
            msg = (f"PO {po_no}: part {part} has no flow in product_workflow_mapping" if not steps
                   else f"PO {po_no}: quantity is 0")
            if explicit:
                raise PoGanttError(422, msg)
            warnings.append(msg + " - not scheduled")
            continue
        pos.append({"po": po_no, "part": part, "qty": c["qty"], "ops": ops_for(part), "idx": len(pos) + 1,
                    "role": role_of(part)})
    if not pos:
        raise PoGanttError(404, "No production orders to schedule")
    for p in pos:
        p["label"] = f"B{p['idx']}" if label_mode == "seq" else p["po"]
    label_idx = {p["label"]: p["idx"] for p in pos}
    label_role = {p["label"]: p["role"] for p in pos}

    # ---------------- stations ----------------
    stations: Dict[str, Station] = {}

    def make_station(op: Dict[str, Any]) -> Station:
        key = op["key"]
        if key in stations:
            return stations[key]
        members = op["steps"]
        sids = [m.flow_step_id for m in members]
        if op["line"]:
            s = Station(key, op["line"], "LINE", sids)
            s.steps = [step_name(m) for m in members]
            s.mode = "LINE"
            counts = [len(equipment[i]) for i in sids if equipment.get(i)]
            n = min(counts) if counts else 1                      # a line is as parallel as its narrowest step
            s.machines = [op["line"]] if n == 1 else [f"{op['line']} #{i + 1}" for i in range(n)]
            s.setup = max([float(cfg[i].setup_minutes or 0) for i in sids if i in cfg], default=0.0)
            s.operators = max(operators_per_shift(i) for i in sids)
            last = cfg.get(sids[-1])
            names = [op["line"]] + s.steps
        else:
            sid = sids[0]
            s = Station(key, step_name(members[0]), "STEP", sids)
            s.mode = "BATCH" if is_batch.get(sid) else "SERIES"
            last = cfg.get(sid)
            if last:
                s.batch_size = max(int(last.batch_size or DEFAULT_BATCH_SIZE), 1)
                s.setup = float(last.setup_minutes or 0)
            s.machines = list(equipment.get(sid, [])) or [f"MANUAL-{sid}"]
            s.operators = operators_per_shift(sid)
            names = [s.name]
        if last:
            s.cooldown = float(last.cooldown_minutes or 0)
            s.cd_working_only = bool(last.cooldown_working_time_only)
            s.next_day_release = bool(last.next_day_release) and bool(is_batch.get(sids[-1]))
        got = capacity_for(names)
        if got:
            s.shifts, s.hps = got
        s.cap_min = min(s.shifts * s.hps * 60.0, 1440.0)
        stations[key] = s
        return s

    for p in pos:
        for op in p["ops"]:
            make_station(op)

    # ---------------- run time of one operation ----------------
    missing_time: Dict[str, List[str]] = defaultdict(list)

    def step_minutes(part: str, st, qty: int) -> Optional[Tuple[float, float]]:
        """(minutes for the whole PO, minutes for the first board / batch) of one routing step."""
        hrs, _src = hours_per_unit(part, st)
        if hrs is None:
            return None
        t = hrs * 60.0
        sid = st.flow_step_id
        if is_batch.get(sid):
            bs = max(int((cfg[sid].batch_size if sid in cfg else 0) or DEFAULT_BATCH_SIZE), 1)
            return math.ceil(qty / bs) * t, t
        return qty * t, t

    def op_minutes(p: Dict[str, Any], op: Dict[str, Any], s: Station) -> float:
        parts = []
        for st in op["steps"]:
            m = step_minutes(p["part"], st, p["qty"])
            if m is None:
                missing_time[p["part"]].append(step_name(st))
                m = (FALLBACK_MINUTES, FALLBACK_MINUTES)
            parts.append(m)
        if len(parts) == 1:
            total = parts[0][0]
        else:                                               # flow line: bottleneck + one board through the rest
            b = max(range(len(parts)), key=lambda i: parts[i][0])
            total = parts[b][0] + sum(parts[i][1] for i in range(len(parts)) if i != b)
        return max(total + s.setup, 1.0)

    # ---------------- child PO -> main PO supply (FIFO by quantity) ----------------
    depends_on: Dict[str, List[str]] = defaultdict(list)
    by_part: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in pos:
        by_part[p["part"]].append(p)
    for main_pn, child_pn in child_of.items():
        mains, childs = by_part.get(main_pn, []), by_part.get(child_pn, [])
        if not mains:
            continue
        if not childs:
            warnings.append(f"Part {main_pn}: no child PO ({child_pn}) loaded - child PCBs assumed in stock, "
                            f"main PO(s) {', '.join(m['label'] for m in mains)} start right away")
            continue
        supply, run = [], 0
        for c in childs:
            supply.append((run, run + c["qty"], c["po"]))
            run += c["qty"]
        need = 0
        for m in mains:
            lo, hi = need, need + m["qty"]
            need = hi
            depends_on[m["po"]] = [cpo for (a, b, cpo) in supply if a < hi and b > lo]
            if hi > run:
                warnings.append(f"PO {m['po']}: needs more child PCBs than the loaded child POs provide - rest assumed in stock")

    def depth(part: str) -> int:
        d = 0
        while part in child_of and d < 10:
            part, d = child_of[part], d + 1
        return d

    # ---------------- schedule (finite capacity) ----------------
    start_day = cal.first_working_day(start_date or today)
    start_dt = datetime.combine(start_day, time.min) + timedelta(hours=shift_start)
    default_cap = min(DEFAULT_SHIFTS * DEFAULT_HOURS_PER_SHIFT * 60.0, 1440.0)

    free_at: Dict[Tuple[str, str], datetime] = defaultdict(lambda: datetime.min)
    usage: Dict[str, Dict[date, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    runs: Dict[Tuple[str, str], List[datetime]] = {}
    po_ready: Dict[str, datetime] = {}
    po_span: Dict[str, List[datetime]] = {}
    route: Dict[str, List[str]] = defaultdict(list)

    for p in sorted(pos, key=lambda x: (ROLES.index(x["role"]), depth(x["part"]), x["idx"])):
        prev_ready = max([start_dt] + [po_ready[c] for c in depends_on.get(p["po"], []) if c in po_ready])
        for op in p["ops"]:
            st = stations[op["key"]]
            minutes = op_minutes(p, op, st)

            best = None
            for mi, mid in enumerate(st.machines):
                s0 = max(prev_ready, free_at[(st.key, mid)])
                if st.kind == "LINE":
                    s, e, eday, segs, same = cal.place_within_day(s0, minutes, st.cap_min)
                else:
                    (s, e, eday, segs), same = cal.consume(s0, minutes, st.cap_min), True
                if best is None or e < best[3]:
                    best = (mi, mid, s, e, eday, segs, same)
            mi, mid, s, e, eday, segs, same = best
            free_at[(st.key, mid)] = e
            if not same:
                warnings.append(f"PO {p['po']} ({p['label']}): {st.name} needs {minutes / 60:.1f} h, more than one "
                                f"working day ({st.cap_min / 60:g} h) - the run is spread over several days")

            for d, a, b, m in segs:
                usage[st.key][d][p["label"]] += m
                segments[st.key].append({
                    "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"], "quantity": p["qty"],
                    "machine": mid, "machine_no": mi, "operation": st.name, "date": d.isoformat(),
                    "start": _iso(a), "end": _iso(b), "minutes": round(m, 1), "run_start": _iso(s), "run_end": _iso(e),
                })
            span = runs.setdefault((st.key, p["label"]), [s, e])
            span[0], span[1] = min(span[0], s), max(span[1], e)
            ps = po_span.setdefault(p["po"], [s, e])
            ps[0], ps[1] = min(ps[0], s), max(ps[1], e)
            row_id = f"{p['role']}:{st.key}"
            if row_id not in route[p["po"]]:
                route[p["po"]].append(row_id)

            ready = e                                            # when the PO may enter the next station
            if st.next_day_release:
                ready = datetime.combine(cal.first_working_day(eday + timedelta(days=1)), time.min) + timedelta(hours=shift_start)
            if st.cooldown > 0:
                if st.cd_working_only:
                    ready = cal.consume(ready, st.cooldown, default_cap)[1]
                else:
                    ready = ready + timedelta(minutes=st.cooldown)
            prev_ready = ready
        po_ready[p["po"]] = prev_ready

    for part, names in missing_time.items():
        uniq = list(dict.fromkeys(names))
        warnings.append(f"Part {part}: no process time for {len(uniq)} step(s) "
                        f"[{', '.join(uniq[:6])}{'...' if len(uniq) > 6 else ''}] - {FALLBACK_MINUTES:g} min used")

    # ---------------- days ----------------
    used_days = [d for per_day in usage.values() for d in per_day]
    last_day = max(used_days + [start_day])
    days, day_no, working_nos = [], {}, 0
    d = start_day
    while d <= last_day:
        if cal.factor(d) > 0:
            working_nos += 1
            day_no[d] = working_nos
            days.append({"working_day_no": working_nos, "date": d.isoformat(), "weekday": d.strftime("%a"),
                         "is_holiday": False, "off_reason": None})
        elif show_holidays:
            days.append({"working_day_no": None, "date": d.isoformat(), "weekday": d.strftime("%a"),
                         "is_holiday": True, "off_reason": cal.off_reason(d)})
        d += timedelta(days=1)

    # ---------------- rows: CHILD section first, then MAIN; each in flow order ----------------
    def part_sort(pn: str):
        prod = products.get(pn)
        return (_key(prod.product_type_name) if prod else "", pn)

    part_order = sorted({p["part"] for p in pos}, key=part_sort)
    section_rows: Dict[str, List[str]] = {r: [] for r in ROLES}
    parts_by_row: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for part in part_order:
        role = role_of(part)
        lst, at = section_rows[role], -1
        for op in ops_for(part):                              # merge the flows of several parts in one section
            if op["key"] in lst:
                at = lst.index(op["key"])
            else:
                at += 1
                lst.insert(at, op["key"])
            if part not in parts_by_row[(role, op["key"])]:
                parts_by_row[(role, op["key"])].append(part)
    roles_of_station: Dict[str, set] = defaultdict(set)
    for role, keys in section_rows.items():
        for k in keys:
            roles_of_station[k].add(role)

    def order_labels(labels) -> List[str]:
        return sorted(labels, key=lambda x: label_idx.get(x, 0))

    def cells_for(key: str, role: str) -> List[Dict[str, Any]]:
        s, out = stations[key], []
        for dd, no in day_no.items():
            u = usage.get(key, {}).get(dd)
            if not u:
                continue
            labels = [lb for lb in u if label_role.get(lb) == role]
            if not labels:
                continue
            out.append({"working_day_no": no, "date": dd.isoformat(), "pos": order_labels(labels),
                        "color": ORANGE if len(labels) >= 2 else BLUE,
                        "minutes_used": round(sum(u[lb] for lb in labels), 1),
                        "station_minutes_used": round(sum(u.values()), 1),
                        "capacity_minutes": round(len(s.machines) * s.cap_min * cal.factor(dd), 1)})
        return out

    def runs_for(key: str, role: str) -> List[Dict[str, str]]:
        out = [(lb, v) for (k, lb), v in runs.items() if k == key and label_role.get(lb) == role]
        return [{"label": lb, "start": _iso(v[0]), "end": _iso(v[1])}
                for lb, v in sorted(out, key=lambda kv: (kv[1][0], label_idx.get(kv[0], 0)))]

    rows: List[Dict[str, Any]] = []
    for role in ROLES:
        for key in section_rows[role]:
            s = stations[key]
            parts = parts_by_row[(role, key)]
            rows.append({
                "row_id": f"{role}:{key}", "station_id": key, "name": s.name, "kind": s.kind, "section": role,
                "role": role, "part_number": parts[0], "part_numbers": parts,
                "flow_step_ids": s.step_ids, "steps": s.steps,
                "shifts": s.shifts, "mins_per_shift": int(s.hps * 60), "machines": len(s.machines),
                "machine_names": s.machines, "operators_per_shift": s.operators, "process_mode": s.mode,
                "shared_with": [r for r in ROLES if r != role and r in roles_of_station[key]],
                "cells": cells_for(key, role), "po_runs": runs_for(key, role),
                "segments": [sg for sg in segments.get(key, []) if sg["role"] == role],
            })

    day_end = shift_start + max((s.cap_min for s in stations.values()), default=default_cap) / 60.0
    line_text = "; ".join(f"{g} = {', '.join(n)}" for g, n in LINE_GROUPS.items())
    assumptions = [
        "Child / main comes from product_type_master (sub product type); a main part is fed by the child part of the same product type.",
        "Each part follows its flow from product_workflow_mapping (step sequence). Child POs are scheduled first; "
        "a main PO starts after the child PO(s) that feed it are finished.",
        "Unit of work is the whole PO quantity; a PO moves through its stations as a block.",
        f"Line stations run in one go inside one working day ({line_text}). "
        "Line time = slowest step for the whole PO + one board through the other steps.",
        f"Shifts per station come from stage_capacity (default {DEFAULT_SHIFTS} x {DEFAULT_HOURS_PER_SHIFT:g} h); "
        f"the day starts at {_hm(shift_start)}.",
        "Off days: Sundays, 1st and 3rd Saturdays, public holidays and calendar 'Holiday' exceptions; "
        "'Working' reopens a day, 'Half-Day' halves it.",
        f"Time per unit = machine time if present, else {'actual' if time_source == 'actual' else 'SAP'} man time "
        "(fallback to the other, routing, stage_capacity).",
        "A station used by child and main POs shows in both sections; the machine capacity is shared.",
        "Operators per shift is informational; it does not limit the schedule.",
    ]
    return {
        "meta": {
            "number_of_pos": len(pos), "start_date": start_day.isoformat(), "finish_date": last_day.isoformat(),
            "working_days": working_nos, "time_source": time_source, "label_mode": label_mode,
            "day_window": {"start_hour": shift_start, "end_hour": round(day_end, 2)},
            "line_groups": {g: list(n) for g, n in LINE_GROUPS.items()},
            "pos": [{"label": p["label"], "production_order": p["po"], "part_number": p["part"], "role": p["role"],
                     "quantity": p["qty"], "depends_on": depends_on.get(p["po"], []), "route": route[p["po"]],
                     "start": _iso(po_span[p["po"]][0]), "end": _iso(po_span[p["po"]][1])} for p in pos],
        },
        "days": days, "stations": rows, "warnings": warnings, "assumptions": assumptions,
    }


# --------------------------------------------------------------------------------------
# Excel export
# --------------------------------------------------------------------------------------
def build_po_gantt_xlsx(result: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    font = lambda **kw: Font(name="Arial", size=10, **kw)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head = PatternFill("solid", start_color="DDE3EE")
    off = PatternFill("solid", start_color="D9D9D9")
    section_fill = {"CHILD": PatternFill("solid", start_color="D3F9D8"), "MAIN": PatternFill("solid", start_color="D0EBFF")}
    fills = {BLUE: PatternFill("solid", start_color="9FC5E8"), ORANGE: PatternFill("solid", start_color="F6B26B")}
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "PO on Station"
    days = result["days"]
    last_col = 2 + len(days)
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 10
    for i, label in enumerate(("Working day #", "Date", "Day"), start=1):
        c = ws.cell(row=i, column=1, value=label)
        c.font, c.fill, c.border = font(bold=True), head, border
        ws.cell(row=i, column=2).fill = head
        ws.cell(row=i, column=2).border = border
    for j, d in enumerate(days, start=3):
        ws.column_dimensions[get_column_letter(j)].width = 11
        dt = date.fromisoformat(d["date"])
        vals = ("Off" if d["is_holiday"] else d["working_day_no"], dt.strftime("%d-%b"), d["weekday"])
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=i, column=j, value=v)
            c.font, c.border, c.alignment = font(bold=(i == 1)), border, center
            c.fill = off if d["is_holiday"] else head
    col_of = {d["working_day_no"]: j for j, d in enumerate(days, start=3) if d["working_day_no"]}

    r, current = 4, None
    for st in result["stations"]:
        if st["section"] != current:
            current = st["section"]
            for j in range(1, last_col + 1):
                c = ws.cell(row=r, column=j)
                c.fill, c.border = section_fill.get(current, head), border
            ws.cell(row=r, column=1, value=f"{current} PROCESSES").font = font(bold=True)
            r += 1
        name = st["name"] + (f"  ({len(st['steps'])} steps, same day)" if st.get("kind") == "LINE" else "")
        a = ws.cell(row=r, column=1, value=name)
        a.font, a.border = font(bold=True), border
        b = ws.cell(row=r, column=2, value=f"{st['shifts']} shift")
        b.font, b.border, b.alignment = font(), border, center
        for j, d in enumerate(days, start=3):
            c = ws.cell(row=r, column=j)
            c.border = border
            if d["is_holiday"]:
                c.fill = off
        for cell in st["cells"]:
            c = ws.cell(row=r, column=col_of[cell["working_day_no"]], value=" ".join(cell["pos"]))
            c.fill, c.font, c.alignment = fills[cell["color"]], font(bold=True), center
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Legend").font = font(bold=True)
    for k, (lab, txt, col) in enumerate((("Blue", "1 PO on the station", BLUE), ("Orange", "2 or more POs share the station", ORANGE)), 1):
        ws.cell(row=r + k, column=1, value=f"{lab}: {txt}").font = font()
        ws.cell(row=r + k, column=2).fill = fills[col]
    r += 4
    for j, h in enumerate(("Label", "Production order", "Part number", "Child / Main", "Quantity", "Start", "End"), start=1):
        c = ws.cell(row=r, column=j, value=h)
        c.font, c.fill, c.border = font(bold=True), head, border
    for k, p in enumerate(result["meta"]["pos"], start=1):
        for j, v in enumerate((p["label"], p["production_order"], p["part_number"], p["role"], p["quantity"],
                               p["start"], p["end"]), start=1):
            c = ws.cell(row=r + k, column=j, value=v)
            c.font, c.border = font(), border
    ws.freeze_panes = "C4"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------------------
def create_po_gantt_router(init_db, verify_token=None, engine=None) -> APIRouter:
    """`engine` is accepted for backward compatibility and no longer used (station_group is not needed)."""
    router = APIRouter()
    deps = [Depends(verify_token)] if verify_token else []

    def _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start):
        try:
            return build_po_gantt(db, production_order, plant, start_date, time_source, label_mode,
                                  show_holidays, shift_start)
        except PoGanttError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)

    @router.get("/schedule/po-gantt/orders", dependencies=deps)
    def po_gantt_orders(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
        return list_open_orders(db, plant)

    @router.get("/schedule/po-gantt", dependencies=deps)
    def po_gantt(
        production_order: Optional[List[str]] = Query(None, description="PO numbers to load; order = load priority"),
        plant: Optional[str] = Query(None),
        start_date: Optional[date] = Query(None, description="default: first working day on/after today"),
        time_source: str = Query("actual"),
        label_mode: str = Query("seq", description="'seq' = B1, B2... | 'po' = PO number"),
        show_holidays: bool = Query(True, description="send off days as flagged columns"),
        shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=10),
        db: Session = Depends(init_db),
    ):
        return _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)

    @router.get("/schedule/po-gantt/export", dependencies=deps)
    def po_gantt_export(
        production_order: Optional[List[str]] = Query(None),
        plant: Optional[str] = Query(None),
        start_date: Optional[date] = Query(None),
        time_source: str = Query("actual"),
        label_mode: str = Query("seq"),
        show_holidays: bool = Query(True),
        shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=10),
        db: Session = Depends(init_db),
    ):
        result = _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)
        return StreamingResponse(
            io.BytesIO(build_po_gantt_xlsx(result)),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="po_gantt.xlsx"'},
        )

    return router