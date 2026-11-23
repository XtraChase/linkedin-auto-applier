"""
Easy Apply form filler for LinkedIn's 2026 application dialog.

Design rules
  * Fills ONLY what your config answers (config/personals.py, config/questions.py) cover.
  * Anything it is not sure about is LEFT UNTOUCHED and you are asked to answer it in the browser.
  * By default it NEVER clicks "Submit application": it stops on the final Review page so you check and submit.
    Only if you turn on auto-submit (--auto-submit / the Run tab checkbox) does it click Submit, and then only when nothing needs a look.
  * Answers LinkedIn pre-filled from your earlier applications are kept (except contact details,
    which are corrected to your config so a stale phone number can't slip through).

Edit SKILL_YEARS below to give specific years for specific skills; everything else that asks
"how many years" gets `years_of_experience` from config/questions.py.
"""
import os, re, time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from answer_audit import risk_flags, summarize, write_log, review_reasons
from answer_memory import Memory
from app_settings import SETTINGS
from config import personals as P
from config import questions as Q

# When the AI has no years figure for a skill in config/profile.md: False = leave it for you to answer,
# True = type the default `years_of_experience` from config/questions.py (can overstate real experience).
# Set it in config/app_settings.json ("years_default_fallback").
YEARS_DEFAULT_FALLBACK = bool(SETTINGS["years_default_fallback"])

# keyword (lower-case, found in the question) -> years to answer. Longest match wins.
SKILL_YEARS = {
    "3d model": "8",
    "3d design": "8",
}

# ---------------------------------------------------------------------------------------------
# JS: read every question on the current page of the dialog and tag each control with data-ea
# ---------------------------------------------------------------------------------------------
ENUM_JS = r"""
const dlg = document.querySelector('dialog'); if (!dlg) return null;
const txt = n => n ? n.innerText.replace(/\s+/g, ' ').trim() : '';
const clean = s => s.replace(/\*+$/, '').trim();
let n = 0;
function labelOf(e) {
  let t = '';
  if (e.id) { const l = dlg.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) t = txt(l); }
  if (!t && e.getAttribute('aria-labelledby')) t = e.getAttribute('aria-labelledby').split(' ').map(i => txt(document.getElementById(i))).join(' ').trim();
  if (!t) t = e.getAttribute('aria-label') || '';
  if (!t) { const p = e.closest('label'); if (p) t = txt(p); }
  if (!t) { let c = e.parentElement; for (let i = 0; i < 4 && c && !t; i++, c = c.parentElement) { const p = c.querySelector('p'); if (p) t = txt(p); } }
  return t;
}
function optionText(r) {
  let c = r.parentElement;
  for (let i = 0; i < 5 && c; i++, c = c.parentElement) { const t = txt(c); if (t) return t; }
  return '';
}
const items = [], radioGroups = {};
for (const e of dlg.querySelectorAll('input,select,textarea')) {
  if (e.type === 'hidden' || e.type === 'file') continue;
  const idx = String(n++); e.setAttribute('data-ea', idx);
  const label = labelOf(e);
  const required = !!(e.required || e.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label));
  if (e.type === 'radio') {
    const g = radioGroups[e.name] || (radioGroups[e.name] = {kind: 'radio', label: clean(label), required: false, options: [], idx: idx});
    g.options.push({idx: idx, text: optionText(e), checked: e.checked});
    g.required = g.required || required || /\*\s*$/.test(txt(e.closest('fieldset') ? e.closest('fieldset').parentElement : null));
    continue;
  }
  if (e.type === 'checkbox') { items.push({kind: 'checkbox', idx: idx, label: clean(label) || optionText(e), checked: e.checked, required: required}); continue; }
  if (e.tagName === 'SELECT') {
    items.push({kind: 'select', idx: idx, label: clean(label), required: required, value: e.value,
      selected: e.selectedIndex >= 0 ? e.options[e.selectedIndex].text.trim() : '', options: [...e.options].map(o => o.text.trim())});
    continue;
  }
  let maxlength = e.maxLength > 0 ? e.maxLength : 0;
  const desc = (e.getAttribute('aria-describedby') || '').split(' ').map(i => txt(document.getElementById(i))).join(' ');
  const mm = desc.match(/of\s+(\d+)\s+characters/i); if (mm) maxlength = parseInt(mm[1]);
  items.push({kind: e.tagName === 'TEXTAREA' ? 'textarea' : 'text', type: e.type, idx: idx, label: clean(label), required: required, value: e.value || '', maxlength: maxlength});
}
for (const k in radioGroups) items.push(radioGroups[k]);
const buttons = [...dlg.querySelectorAll('button')].filter(b => b.offsetParent).map(b => txt(b) || b.getAttribute('aria-label') || '');
const progress = (txt(dlg).match(/\d+\s*\/\s*\d+\s*pages?/i) || [''])[0];
const resumeRadios = items.filter(i => i.kind === 'radio' && i.options.some(o => /\.(pdf|docx?)\b/i.test(o.text)));
const resumes = resumeRadios.flatMap(g => g.options.map(o => ({idx: o.idx, text: o.text, checked: o.checked})));
// file upload controls: work out whether each one is for a cover letter or a resume from the text around it
const files = [...dlg.querySelectorAll("input[type=file]")].map((e, i) => {
  const id = "f" + i; e.setAttribute("data-ea-file", id);
  const own = [e.getAttribute("aria-label"), e.id, e.name, e.getAttribute("accept")].join(" ");
  let kind = "other", ctx = own;
  const decide = t => {
    const cov = /cover\s*letter/i.test(t), res = /resume|\bcv\b/i.test(t);
    if (cov && !res) return "cover"; if (res && !cov) return "resume"; if (cov && res) return "both"; return "";
  };
  let k = decide(own);
  for (let c = e.parentElement, n = 0; !k && n < 7 && c; c = c.parentElement, n++) {
    const t = txt(c); if (!t) continue; ctx = t.slice(0, 160); k = decide(t);
  }
  if (k === "cover" || k === "resume") kind = k;
  return {idx: id, kind: kind, label: ctx, accept: e.accept || "", hasFile: !!(e.files && e.files.length)};
});
return {items: items.filter(i => !resumeRadios.includes(i)), resume_page: resumeRadios.length > 0, resumes: resumes, files: files, buttons: buttons, progress: progress,
        text: dlg.innerText.slice(0, 3000), sig: progress + '|' + items.map(i => i.kind + i.idx).join(',') + '|' + buttons.join(',')};
"""


def digits(s):
    return re.sub(r"\D", "", s or "")


def yes_no(v):
    return "yes" if str(v).strip().lower() in ("yes", "true", "y") else "no"


def years_for(label):
    L = label.lower()
    best = None
    for k, v in SKILL_YEARS.items():
        if k in L and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else str(Q.years_of_experience)


YEARS_RE = r"years?\b.*(experience|work)|experience.*years|how many years"


def decide(it):
    """Answer from your config rules, or None when we should not guess."""
    L = it["label"].lower()
    kind = it["kind"]

    # ---- contact details -------------------------------------------------------------------
    if re.search(r"first name", L): return P.first_name
    if re.search(r"last name|surname|family name", L): return P.last_name
    if re.search(r"middle name", L): return P.middle_name or None
    if re.search(r"phone country|country code", L): return "United States" if "united states" in P.country.lower() else None
    if re.search(r"phone|mobile", L) and kind == "text": return digits(P.phone_number)
    if re.search(r"^e-?mail", L): return None                     # LinkedIn's own verified email stays
    if re.search(r"city|location", L) and kind == "text": return P.current_city or None
    if re.search(r"street|address line|^address", L): return P.street or None
    if re.search(r"zip|postal", L): return P.zipcode or None
    if re.search(r"^state\b|province", L): return P.state or None
    if re.search(r"linkedin", L): return Q.linkedIn or None
    if re.search(r"website|portfolio|github|personal site|\burl\b", L): return Q.website or None
    if re.search(r"cover letter", L): return (Q.cover_letter or "").strip() or None
    if re.search(r"headline", L): return Q.linkedin_headline or None
    if re.search(r"summary", L): return (Q.linkedin_summary or "").strip() or None
    # ---- pay -------------------------------------------------------------------------------
    if re.search(r"(desired|expected|expectation|target).*(salary|compensation|pay)|salary expectation", L): return str(Q.desired_salary)
    if re.search(r"current.*(salary|compensation|pay|ctc)", L): return str(Q.current_ctc) if Q.current_ctc else None
    # ---- work authorisation ----------------------------------------------------------------
    if re.search(r"sponsor", L): return "Yes" if yes_no(Q.require_visa) == "yes" else "No"
    if re.search(r"(authori[sz]ed|legally|eligible|right).*work|work.*(authori[sz]ation|legally)", L): return "Yes" if yes_no(Q.legally_authorized) == "yes" else "No"
    if re.search(r"citizen", L) and kind in ("select", "radio"): return Q.us_citizenship
    # ---- years of experience ---------------------------------------------------------------
    if re.search(YEARS_RE, L) and kind in ("text", "textarea"):
        # only answer from config for a skill with its own SKILL_YEARS entry, or when the fallback switch is on
        if YEARS_DEFAULT_FALLBACK or any(k in L for k in SKILL_YEARS): return years_for(it["label"])
        return None
    # ---- equal opportunity -----------------------------------------------------------------
    if re.search(r"gender|sex\b", L): return P.gender or None
    if re.search(r"\brace\b|ethnic", L): return P.ethnicity or None
    if re.search(r"veteran", L): return P.veteran_status or None
    if re.search(r"disab", L): return P.disability_status or None
    return None


def match_option(answer, options):
    """Index of the option that best matches `answer`, or None."""
    a = answer.lower().strip()
    texts = [o.lower().strip() for o in options]
    if a == "united states":                      # not "United States Minor Outlying Islands"
        for i, t in enumerate(texts):
            if re.match(r"^united states \(\+1\)", t): return i
    if a == "decline":
        for i, t in enumerate(texts):
            if re.search(r"decline|prefer not|don'?t wish|do not wish|not to (say|answer|disclose)", t): return i
        return None
    for i, t in enumerate(texts):
        if t == a: return i
    for i, t in enumerate(texts):
        if a and (a in t or (t and t in a and len(t) > 2)): return i
    return None


def pick_resume(title, resumes, preferred="", rules=()):
    """Index into `resumes` of the resume to select for this job, or None to keep LinkedIn's selection.
    Rules are [job-title regex, resume-name regex] pairs, first match wins; then `preferred` for every job."""
    def find(pattern):
        try:
            rx = re.compile(pattern, re.I)
        except re.error:
            return None
        for i, r in enumerate(resumes):
            if rx.search(r["text"]): return i
        return None
    for pair in rules or []:
        try:
            tpat, rpat = pair
        except (TypeError, ValueError):
            continue
        if re.search(tpat, title or "", re.I):
            k = find(rpat)
            if k is not None: return k
    if preferred:
        return find(preferred)
    return None


def _follow_cfg():
    try:
        from config import settings as ST
        return bool(ST.follow_companies)
    except Exception:
        return False


class Filler:
    def __init__(self, driver, log=print, ai=None, job=None, memory=None, auto_submit=False, review_pause=True):
        self.d = driver
        self.log = log
        self.ai = ai                         # AIAnswerer or None
        self.job = job or {}
        self.memory = memory if memory is not None else Memory()
        self.answers = []                    # audit rows: {q, a, source, flags}
        self.auto_submit = auto_submit       # opt-in: click Submit for you when nothing needs a look
        self.review_pause = review_pause     # with auto_submit: still stop for you when an answer needs a look
        self.left_blank = []                 # questions nothing supported an answer for

    # ---- audit ---------------------------------------------------------------------------
    def rec(self, label, answer, source):
        row = {"q": label, "a": str(answer), "source": source, "flags": risk_flags(label, str(answer), source)}
        for i, old in enumerate(self.answers):
            if old["q"] == label:
                self.answers[i] = row; return
        self.answers.append(row)

    def _answer_for(self, label):
        for r in self.answers:
            if r["q"] == label: return r["a"]
        return None

    # ---- low-level -----------------------------------------------------------------------
    def dialog_open(self):
        return self.d.execute_script("return !!document.querySelector('dialog')")

    def page(self):
        return self.d.execute_script(ENUM_JS)

    def el(self, idx):
        return self.d.find_element(By.CSS_SELECTOR, f'[data-ea="{idx}"]')

    def set_text(self, idx, value):
        e = self.el(idx)
        self.d.execute_script("arguments[0].scrollIntoView({block:'center'});", e)
        e.click()
        e.send_keys(Keys.CONTROL, "a")
        e.send_keys(Keys.DELETE)
        e.send_keys(value)
        e.send_keys(Keys.TAB)

    def set_select(self, idx, option_index):
        Select(self.el(idx)).select_by_index(option_index)

    def click_radio(self, idx):
        self.d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", self.el(idx))

    def set_checkbox(self, idx, want):
        e = self.el(idx)
        if e.is_selected() != want:
            self.d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", e)

    def click_button(self, text):
        return self.d.execute_script(
            "const b=[...document.querySelectorAll('dialog button')].find(x=>x.innerText.trim()===arguments[0]); if(b){b.click();return true;} return false;", text)

    # ---- one page ------------------------------------------------------------------------
    def fill_page(self, pg):
        """Fill what we know on the current page. Returns (filled, unanswered)."""
        filled, unanswered = [], []
        for it in pg["items"]:
            kind, label = it["kind"], it["label"]
            L = label.lower()
            if kind == "checkbox":
                if re.match(r"follow\b", label, re.I) and it["checked"] and not _follow_cfg():
                    self.set_checkbox(it["idx"], False)
                    filled.append(f'unticked "{label}"'); self.rec(label, "unticked", "config")
                continue
            is_contact = bool(re.search(r"first name|last name|phone|mobile", L))
            is_years = bool(re.search(YEARS_RE, L)) and kind in ("text", "textarea")
            options = [o["text"] for o in it["options"]] if kind == "radio" else (it["options"] if kind == "select" else None)
            mem = None if is_contact else self.memory.get(label, kind, options)
            cfg = decide(it)
            pick, src = (mem, "memory") if mem is not None else (cfg, "config")

            if kind == "radio":
                k = match_option(pick, options) if pick else None
                if k is not None:
                    if not it["options"][k]["checked"]: self.click_radio(it["options"][k]["idx"])
                    filled.append(f'{label} -> {options[k]}  [{src}]'); self.rec(label, options[k], src); continue
                chosen = [o for o in it["options"] if o["checked"]]
                if chosen:
                    filled.append(f'{label} -> {chosen[0]["text"]}  [kept from LinkedIn]'); self.rec(label, chosen[0]["text"], "kept"); continue
                a = self.ai.answer(it) if self.ai else None
                k = match_option(a, options) if a else None
                if k is not None:
                    self.click_radio(it["options"][k]["idx"])
                    filled.append(f'{label} -> {options[k]}  [AI]'); self.rec(label, options[k], "ai")
                else:
                    unanswered.append(label)
                continue

            if kind == "select":
                k = match_option(pick, options) if pick else None
                if k is not None:
                    if options[k] != it["selected"]: self.set_select(it["idx"], k)
                    filled.append(f'{label} -> {options[k]}  [{src}]'); self.rec(label, options[k], src); continue
                if it["selected"] and it["selected"].strip(" -").lower() not in ("select an option", "select", ""):
                    filled.append(f'{label} -> {it["selected"]}  [kept]'); self.rec(label, it["selected"], "kept"); continue
                a = self.ai.answer(it) if self.ai else None
                k = match_option(a, options) if a else None
                if k is not None:
                    self.set_select(it["idx"], k)
                    filled.append(f'{label} -> {options[k]}  [AI]'); self.rec(label, options[k], "ai")
                elif it["required"]:
                    unanswered.append(label)
                continue

            # ---- text / textarea ----
            cur = it["value"]
            if is_contact:                                   # contact details always come from your config
                if cfg:
                    same = (digits(cur) == digits(cfg)) if re.search(r"phone|mobile", L) else (cur.strip() == cfg.strip())
                    if not same: self.set_text(it["idx"], cfg)
                    filled.append(f'{label} -> {cfg}' + (f' (was "{cur}")' if cur and not same else "")); self.rec(label, cfg, "config")
                elif it["required"] and not cur.strip():
                    unanswered.append(label)
                continue
            if mem is not None:
                if cur.strip() != mem.strip(): self.set_text(it["idx"], mem)
                filled.append(f'{label} -> {mem}  [remembered]'); self.rec(label, mem, "memory"); continue
            if cur.strip():                                  # LinkedIn pre-filled it from an earlier application
                filled.append(f'{label} -> {cur}  [kept from LinkedIn]'); self.rec(label, cur, "kept"); continue
            if re.search(r"city|location", L) and not it["required"]:
                continue                                     # optional city box can be a typeahead; leave it alone
            if is_years and self.ai:
                a = self.ai.answer(it)
                use, usrc = (a, "ai") if a else (cfg, "default-years" if cfg and not any(k in L for k in SKILL_YEARS) else "config")
                if use:
                    self.set_text(it["idx"], use)
                    filled.append(f'{label} -> {use}  [{"AI" if a else "default years"}]'); self.rec(label, use, usrc)
                elif it["required"]:
                    unanswered.append(label)
                continue
            if re.search(r"cover letter|letter of interest", L) and not cfg and self.ai and SETTINGS["cover_letter"] == "ai":
                letter = self.ai.cover_letter(int(it.get("maxlength") or 0))
                if letter:
                    self.set_text(it["idx"], letter)
                    filled.append(f'{label} -> (AI-written cover letter, {len(letter.split())} words)  [AI]'); self.rec(label, letter, "ai"); continue
            if cfg:
                self.set_text(it["idx"], cfg)
                csrc ="default-years" if is_years and not any(k in L for k in SKILL_YEARS) else "config"
                filled.append(f'{label} -> {cfg if len(cfg) < 90 else cfg[:87] + "..."}  [{csrc}]'); self.rec(label, cfg, csrc); continue
            a = self.ai.answer(it) if self.ai else None
            if a:
                self.set_text(it["idx"], a)
                filled.append(f'{label} -> {a if len(a) < 90 else a[:87] + "..."}  [AI]'); self.rec(label, a, "ai")
            elif it["required"]:
                unanswered.append(label)
        return filled, unanswered

    # ---- file uploads (cover letter as a PDF) ----------------------------------------------
    def handle_uploads(self, pg):
        """When the form asks for a cover letter FILE, write one as a PDF and upload it. Returns questions we could not do."""
        todo = [f for f in pg.get("files", []) if f["kind"] == "cover" and not f["hasFile"]]
        if not todo: return []
        label = "Cover letter (PDF upload)"
        self._dump_upload_page(pg)
        if SETTINGS["cover_letter"] != "ai" or not self.ai:
            self.log("   >> This form asks for a cover letter file. Cover letters are off (or AI is off), so please upload one yourself.")
            return [label]
        letter = self.ai.cover_letter(0)
        if not letter:
            self.log("   >> The AI could not write a cover letter for this job; please upload one yourself.")
            return [label]
        try:
            from cover_letter_pdf import make_pdf
            path = make_pdf(letter, self.job)
        except Exception as e:
            self.log(f"   >> Could not make the cover letter PDF ({type(e).__name__}); please upload one yourself.")
            return [label]
        self.log(f"   cover letter PDF written: {path}")
        failed = []
        for f in todo:
            if self._upload_file(f["idx"], path):
                self.log(f"   cover letter uploaded: {os.path.basename(path)}  [AI]")
                self.rec(label, os.path.basename(path), "ai"); self.rec("Cover letter text", letter, "ai")
            else:
                self.log(f"   >> The upload did not take. Please upload this file yourself: {path}")
                failed.append(label)
        return failed

    def _upload_file(self, file_idx, path):
        """Put a file into the form's file input (shown first if the page keeps it hidden). True when the browser accepted it."""
        try:
            el = self.d.find_element(By.CSS_SELECTOR, f'[data-ea-file="{file_idx}"]')
            self.d.execute_script("const e = arguments[0]; e.removeAttribute('hidden'); const s = e.style; s.display = 'block'; s.visibility = 'visible'; s.opacity = '1'; "
                                  "s.position = 'fixed'; s.left = '0'; s.top = '0'; s.width = '20px'; s.height = '20px'; s.zIndex = '99999';", el)
            el.send_keys(path)
            time.sleep(1.5)
            for _ in range(10):
                if self.d.execute_script("const e = document.querySelector('[data-ea-file=\"" + file_idx + "\"]'); return !!(e && e.files && e.files.length);"):
                    time.sleep(2.0)                       # let LinkedIn finish its own upload step
                    return True
                time.sleep(0.5)
        except Exception as e:
            self.log(f"   (upload error: {type(e).__name__})")
        return False

    def _dump_upload_page(self, pg):
        """Keep the HTML of a form that has a cover letter upload, so a broken upload can be diagnosed later (stays on this computer)."""
        try:
            import app_paths
            folder = os.path.join(app_paths.home(), "reports"); os.makedirs(folder, exist_ok=True)
            html = self.d.execute_script("const x = document.querySelector('dialog'); return x ? x.outerHTML : ''")
            open(os.path.join(folder, f"upload_form_{self.job.get('id', 'job')}.html"), "w", encoding="utf-8").write(html or "")
        except Exception:
            pass

    # ---- learning from what you type -------------------------------------------------------
    def _values(self, pg):
        out = {}
        for it in pg["items"]:
            k = it["kind"]
            if k in ("text", "textarea"): v = it["value"]
            elif k == "select": v = it["selected"]
            elif k == "radio":
                c = [o["text"] for o in it["options"] if o["checked"]]; v = c[0] if c else ""
            else: continue
            out[it["label"]] = (k, (v or "").strip())
        return out

    def _learn_from(self, snap):
        """Save answers you typed (or changed) while the bot was waiting, so next time they are filled for you."""
        for label, (kind, val) in snap.items():
            if not val or re.search(r"first name|last name|phone|mobile|e-?mail", label.lower()): continue
            before = self._answer_for(label)
            if before is not None and before.strip() == val: continue
            if self.memory.learn(label, val, kind):
                self.log(f'   (remembered your answer: "{label[:70]}" -> "{val[:60]}")')
            self.rec(label, val, "you")

    # ---- whole form ----------------------------------------------------------------------
    def run(self, wait_seconds=25 * 60):
        """Walk the form, filling what we can. Stops on the Submit page (submits only with auto_submit).
        Returns 'applied' | 'closed' | 'stopped at review ...'."""
        t0 = time.time()
        last_sig, page_no = None, 0
        while time.time() - t0 < wait_seconds:
            if not self.dialog_open():
                return "closed"
            pg = self.page()
            if pg is None: return "closed"
            if re.search(r"application (was )?sent", pg["text"], re.I): return "applied"
            if not any(b and b != "Dismiss" for b in pg["buttons"]):   # dialog still rendering
                time.sleep(1); continue
            if pg["sig"] == last_sig:
                time.sleep(1); continue
            last_sig = pg["sig"]; page_no += 1
            buttons = pg["buttons"]
            final = "Submit application" in buttons
            self.log(f'   --- page {page_no} {pg["progress"]} buttons={[b for b in buttons if b and b != "Dismiss"]}')
            if pg["resume_page"]:
                k = pick_resume(self.job.get("title", ""), pg.get("resumes", []), SETTINGS["preferred_resume"], SETTINGS["resume_rules"])
                if k is not None:
                    r = pg["resumes"][k]
                    if not r["checked"]: self.click_radio(r["idx"])
                    self.log(f'   resume: selected "{r["text"][:70]}" (your resume rule)'); self.rec("Resume", r["text"][:80], "config")
                else:
                    cur = [r["text"] for r in pg.get("resumes", []) if r["checked"]]
                    self.log("   resume: keeping the one LinkedIn selected" + (f' ("{cur[0][:60]}")' if cur else ""))
            filled, unanswered = self.fill_page(pg)
            for f in filled: self.log("   filled:", f)
            unanswered = unanswered + self.handle_uploads(pg)
            self.left_blank += [u for u in unanswered if u not in self.left_blank]
            if final:
                summarize(self.answers, self.log)
                if self.auto_submit:
                    return self._auto_submit(t0, wait_seconds)
                write_log(self.job, self.answers, "reached submit page")
                self.log("   >> SUBMIT PAGE reached. Check everything, then click 'Submit application' yourself (or close the form to skip).")
                return self._wait_closed(t0, wait_seconds)
            if unanswered:
                self.log("   >> I could not answer these (nothing in your profile supports an answer); trying Next anyway:")
                for u in unanswered: self.log("        -", u)
            nxt = "Next" if "Next" in buttons else ("Review" if "Review" in buttons else None)
            if nxt is None:
                self.log("   >> No Next/Review button found; please continue by hand.")
                last_sig = self._wait_page_change(pg["sig"], t0, wait_seconds); continue
            time.sleep(1)
            self.click_button(nxt)
            time.sleep(2.5)
            after = self.page()
            if after is not None and after["sig"] == pg["sig"]:
                self.log("   >> LinkedIn did not accept this page (a required answer is missing or wrong). Please answer it in the browser and click Next.")
                for u in unanswered: self.log("        - still needs:", u)
                last_sig = self._wait_page_change(pg["sig"], t0, wait_seconds, learn=True)
            else:
                last_sig = None                          # new page: loop will process it
        return "closed"

    def _auto_submit(self, t0, wait_seconds):
        """Opt-in: click 'Submit application' ourselves when nothing needs a human look, confirm LinkedIn accepted it,
        close the confirmation and return so the run moves on. Otherwise fall back to waiting for you."""
        reasons = review_reasons(self.answers, self.left_blank) if self.review_pause else []
        if reasons:
            write_log(self.job, self.answers, "reached submit page (auto-submit held back)")
            self.log("   >> AUTO-SUBMIT HELD BACK: this one needs your eyes:")
            for r in reasons[:6]: self.log("        -", r)
            self.log("   >> SUBMIT PAGE reached. Check everything, then click 'Submit application' yourself (or close the form to skip).")
            return self._wait_closed(t0, wait_seconds)
        self.log("   >> AUTO-SUBMIT: submitting this application now.")
        if not self.click_button("Submit application"):
            self.log("   >> Could not find the Submit button; please submit it yourself.")
            write_log(self.job, self.answers, "reached submit page (submit button not found)")
            return self._wait_closed(t0, wait_seconds)
        for _ in range(30):                                   # up to ~30 s for LinkedIn to confirm
            time.sleep(1)
            t = self.d.execute_script("const x=document.querySelector('dialog'); return x? x.innerText : null;")
            if t is None: break                               # dialog gone: treated below
            if re.search(r"application (was )?sent", t, re.I):
                write_log(self.job, self.answers, "auto-submitted")
                self.log("   >> Application sent (LinkedIn confirmed). Closing the confirmation.")
                for label in ("Done", "Dismiss"):
                    if self.click_button(label): break
                time.sleep(1)
                if self.dialog_open():
                    self.d.execute_script("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}));")
                return "applied"
        write_log(self.job, self.answers, "auto-submit not confirmed")
        self.log("   >> LinkedIn did not confirm the submission (a required answer may be missing). Please check the browser and finish it by hand.")
        return self._wait_closed(t0, wait_seconds)

    def _wait_page_change(self, sig, t0, limit, learn=False):
        snap = {}
        while time.time() - t0 < limit:
            if not self.dialog_open(): break
            pg = self.page()
            if pg is None or pg["sig"] != sig: break
            if learn: snap = self._values(pg)
            time.sleep(1)
        if learn and snap: self._learn_from(snap)
        return None

    def _wait_closed(self, t0, limit):
        sent = False
        while time.time() - t0 < limit:
            t = self.d.execute_script("const x=document.querySelector('dialog'); return x? x.innerText : null;")
            if t is None: break
            if re.search(r"application (was )?sent", t, re.I): sent = True
            time.sleep(1)
        return "applied" if sent else "stopped at review (closed, not submitted)"
