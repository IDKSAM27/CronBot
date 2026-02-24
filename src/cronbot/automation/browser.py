import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Callable

from playwright.sync_api import BrowserContext

class DiaryAutomator:
    """Handles the Playwright browser automation logic."""
    
    def __init__(self, p: Any, config: dict, status_logger: Callable[[str], None]):
        self.config = config
        self.log = status_logger
        
        self.log("Launching browser engine...")
        self.browser = p.chromium.launch(headless=False) 
        self.context = self._get_browser_context()
        self.page = self.context.new_page()

    def _get_browser_context(self) -> BrowserContext:
        if self.config["STATE_FILE"].exists():
            self.log("Found saved browser state (Cookies loaded).")
            return self.browser.new_context(storage_state=str(self.config["STATE_FILE"]))
        
        self.log("No saved state found. Will perform fresh login.")
        return self.browser.new_context()

    def _parse_target_date(self, target_date: str) -> tuple[int, int, int]:
        """Parses DD-MM-YYYY date into day, month, year integers."""
        try:
            parsed = datetime.strptime(target_date, "%d-%m-%Y")
            return parsed.day, parsed.month, parsed.year
        except ValueError as e:
            raise ValueError("Invalid date format. Expected DD-MM-YYYY.") from e

    def _read_date_input_value(self) -> str:
        """Reads current value from the diary date input if present."""
        candidates = self.page.locator(
            "input[placeholder*='Pick a Date'], input[name*='date' i], input[id*='date' i]"
        )
        count = candidates.count()
        for idx in range(min(count, 5)):
            field = candidates.nth(idx)
            try:
                value = field.input_value().strip()
                if value:
                    return value
            except Exception:
                continue
        return ""

    def _wait_for_continue_enabled(self, timeout_ms: int = 5000) -> bool:
        """Waits until Continue button is enabled."""
        continue_button = self.page.locator("button:has-text('Continue')").first
        deadline = datetime.now().timestamp() + (timeout_ms / 1000.0)
        while datetime.now().timestamp() < deadline:
            try:
                if continue_button.is_enabled():
                    return True
            except Exception:
                pass
            self.page.wait_for_timeout(200)
        return False

    def _is_day_marked_selected(self, calendar, day: int, month: int, year: int) -> bool:
        """Checks if target day appears selected in the calendar."""
        month_name = datetime(year, month, 1).strftime("%B").lower()
        return bool(
            calendar.evaluate(
                """
                (root, payload) => {
                  const wanted = String(payload.day);
                  const monthName = String(payload.monthName || "").toLowerCase();
                  const year = String(payload.year || "");
                  const selectedCandidates = Array.from(
                    root.querySelectorAll(
                      "[aria-selected='true'], .react-datepicker__day--selected, .rdp-day_selected, .selected"
                    )
                  );
                  return selectedCandidates.some((el) => {
                    const text = (el.textContent || "").trim();
                    if (text !== wanted) return false;
                    const aria = (el.getAttribute("aria-label") || "").toLowerCase();
                    if (!aria) return true;
                    if (monthName && !aria.includes(monthName)) return false;
                    if (year && !aria.includes(year)) return false;
                    return true;
                  });
                }
                """,
                {"day": day, "monthName": month_name, "year": str(year)},
            )
        )

    def _try_click_day_candidates(self, calendar, candidates, day: int, month: int, year: int) -> bool:
        """Tries candidate locators and returns True if selection is accepted."""
        candidate_count = candidates.count()
        for idx in range(candidate_count):
            node = candidates.nth(idx)
            try:
                if not node.is_visible():
                    continue
            except Exception:
                continue

            try:
                is_disabled = node.is_disabled()
            except Exception:
                is_disabled = False
            if is_disabled:
                continue

            try:
                flags = (node.evaluate(
                    """
                    (el) => {
                      const own = (el.className || "").toString().toLowerCase();
                      const parent = (el.parentElement?.className || "").toString().toLowerCase();
                      const td = (el.closest('td')?.className || "").toString().toLowerCase();
                      const gridcell = (el.closest('[role=\"gridcell\"]')?.className || "").toString().toLowerCase();
                      const ariaDisabled = (el.getAttribute('aria-disabled') || '').toLowerCase();
                      return `${own} ${parent} ${td} ${gridcell} ${ariaDisabled}`;
                    }
                    """
                ) or "").lower()
                if any(flag in flags for flag in ["outside", "disabled", "muted", "aria-disabled"]):
                    continue
            except Exception:
                pass

            try:
                node.click(timeout=1500)
            except Exception:
                continue

            self.page.wait_for_timeout(250)
            if self._wait_for_continue_enabled(timeout_ms=1200):
                self.log(f"Day selected: {day:02d}")
                return True
            try:
                if self._is_day_marked_selected(calendar, day, month, year):
                    self.log(f"Day selected: {day:02d}")
                    return True
            except Exception:
                pass

        return False

    def _find_datepicker_root(self):
        """
        Locates the visible React datepicker root.
        Uses a class-based selector first, with a broad fallback.
        """
        try:
            self.page.wait_for_selector(".react-datepicker:visible", timeout=5000)
            return self.page.locator(".react-datepicker:visible").first
        except Exception:
            pass

        # Fallback: prefer a visible container that has at least 2 visible selects (month + year).
        candidates = self.page.locator("div:has(select:visible):visible")
        candidate_count = candidates.count()
        for idx in range(candidate_count):
            candidate = candidates.nth(idx)
            if candidate.locator("select:visible").count() >= 2:
                return candidate

        if candidate_count > 0:
            return candidates.first

        calendar = self.page.locator("div:has(select):visible").first
        if calendar.count() == 0:
            raise RuntimeError("Could not locate the datepicker popup after clicking date field.")
        return calendar

    def _select_option_texts(self, select_locator, max_options: int = 40) -> list[str]:
        options = select_locator.locator("option")
        option_count = options.count()
        texts: list[str] = []
        for idx in range(min(option_count, max_options)):
            text = options.nth(idx).inner_text().strip()
            if text:
                texts.append(text)
        return texts

    def _looks_like_month_select(self, select_locator) -> bool:
        month_tokens = {
            "jan",
            "january",
            "feb",
            "february",
            "mar",
            "march",
            "apr",
            "april",
            "may",
            "jun",
            "june",
            "jul",
            "july",
            "aug",
            "august",
            "sep",
            "sept",
            "september",
            "oct",
            "october",
            "nov",
            "november",
            "dec",
            "december",
        }
        texts = [t.lower() for t in self._select_option_texts(select_locator)]
        hits = sum(1 for t in texts if t in month_tokens)
        return hits >= 3

    def _looks_like_year_select(self, select_locator, year: int) -> bool:
        texts = self._select_option_texts(select_locator)
        if str(year) in texts:
            return True
        year_like = [t for t in texts if t.isdigit() and len(t) == 4]
        return len(year_like) >= 2

    def _candidate_selects(self, calendar):
        """Returns visible select candidates, preferring those inside the calendar root."""
        seen_ids: set[int] = set()
        candidates = []

        local = calendar.locator("select:visible")
        for idx in range(local.count()):
            loc = local.nth(idx)
            oid = id(loc)
            if oid not in seen_ids:
                candidates.append(loc)
                seen_ids.add(oid)

        global_visible = self.page.locator("select:visible")
        for idx in range(global_visible.count()):
            loc = global_visible.nth(idx)
            oid = id(loc)
            if oid not in seen_ids:
                candidates.append(loc)
                seen_ids.add(oid)

        return candidates

    def _select_datepicker_year(self, calendar, year: int):
        """Selects target year from the datepicker year dropdown."""
        selection_attempts = [
            {"value": str(year)},
            {"label": str(year)},
        ]

        explicit_year = calendar.locator("select.react-datepicker__year-select:visible").first
        candidate_selects = []
        if explicit_year.count() > 0:
            candidate_selects.append(explicit_year)

        candidate_selects.extend(
            select for select in self._candidate_selects(calendar) if self._looks_like_year_select(select, year)
        )

        if not candidate_selects:
            raise RuntimeError("Could not find a visible year dropdown in the datepicker.")

        last_error = None
        for year_select in candidate_selects:
            for attempt in selection_attempts:
                try:
                    year_select.select_option(**attempt)
                    self.log(f"Year selected: {year}")
                    return
                except Exception as e:
                    last_error = e

        raise RuntimeError(f"Could not select year {year} from datepicker dropdown.") from last_error

    def _select_datepicker_month(self, calendar, month: int):
        """Selects target month from the datepicker month dropdown."""
        label_fallbacks = {
            1: ["Jan", "January"],
            2: ["Feb", "February"],
            3: ["Mar", "March"],
            4: ["Apr", "April"],
            5: ["May"],
            6: ["Jun", "June"],
            7: ["Jul", "July"],
            8: ["Aug", "August"],
            9: ["Sep", "Sept", "September"],
            10: ["Oct", "October"],
            11: ["Nov", "November"],
            12: ["Dec", "December"],
        }

        selection_attempts = [
            {"value": str(month - 1)},  # default react-datepicker values: 0-11
            {"value": str(month)},      # fallback for custom values: 1-12
        ]
        for label in label_fallbacks[month]:
            selection_attempts.append({"label": label})

        explicit_month = calendar.locator("select.react-datepicker__month-select:visible").first
        candidate_selects = []
        if explicit_month.count() > 0:
            candidate_selects.append(explicit_month)

        candidate_selects.extend(
            select for select in self._candidate_selects(calendar) if self._looks_like_month_select(select)
        )

        if not candidate_selects:
            raise RuntimeError("Could not find a visible month dropdown in the datepicker.")

        last_error = None
        for month_select in candidate_selects:
            for attempt in selection_attempts:
                try:
                    month_select.select_option(**attempt)
                    self.log(f"Month selected: {month:02d}")
                    return
                except Exception as e:
                    last_error = e

            # Index fallback only for controls that look like real month dropdowns.
            try:
                option_count = month_select.locator("option").count()
                if option_count >= 12:
                    month_select.select_option(index=month - 1)
                    self.log(f"Month selected: {month:02d}")
                    return
            except Exception as e:
                last_error = e

        raise RuntimeError(f"Could not select month {month} from datepicker dropdown.") from last_error

    def _click_datepicker_day(self, calendar, day: int, month: int, year: int):
        """Clicks the day cell for the currently selected month/year."""
        month_name = datetime(year, month, 1).strftime("%B")
        iso_date = f"{year:04d}-{month:02d}-{day:02d}"
        day_text_regex = re.compile(rf"^\s*{day}\s*$")

        # 1) Deterministic selectors (date-value / date-data attributes)
        attribute_candidates = calendar.locator(
            (
                f"button[value='{iso_date}'], "
                f"button[data-day='{iso_date}'], "
                f"button[data-date='{iso_date}'], "
                f"[data-day='{iso_date}'], "
                f"[data-date='{iso_date}']"
            )
        )
        if self._try_click_day_candidates(calendar, attribute_candidates, day, month, year):
            return

        # 2) React-datepicker-specific day class selectors
        react_candidates = calendar.locator(
            (
                f".react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)"
                ":not(.react-datepicker__day--disabled):not([aria-disabled='true'])"
            )
        )
        if self._try_click_day_candidates(calendar, react_candidates, day, month, year):
            return

        # 3) Accessible-name candidates (month/year-aware)
        named_buttons = calendar.get_by_role("button", name=re.compile(rf"{month_name}.*{day}.*{year}", re.I))
        if self._try_click_day_candidates(calendar, named_buttons, day, month, year):
            return

        alt_named_buttons = calendar.get_by_role("button", name=re.compile(rf"{day}.*{month_name}.*{year}", re.I))
        if self._try_click_day_candidates(calendar, alt_named_buttons, day, month, year):
            return

        # 4) Generic button text fallback (exact day number)
        text_buttons = calendar.locator("button").filter(has_text=day_text_regex)
        if self._try_click_day_candidates(calendar, text_buttons, day, month, year):
            return

        # 5) JS fallback: inspect visible day buttons/gridcells only (not generic spans/divs).
        clicked = bool(calendar.evaluate(
            """
            (root, payload) => {
              const wanted = String(payload.day);
              const monthName = String(payload.monthName || "");
              const year = String(payload.year || "");
              const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                return style.visibility !== "hidden" && style.display !== "none" && !!el.offsetParent;
              };
              const isDisabled = (el) => {
                const cls = (el.className || "").toString().toLowerCase();
                const parentCls = (el.parentElement?.className || "").toString().toLowerCase();
                const tdCls = (el.closest("td")?.className || "").toString().toLowerCase();
                return (
                  el.hasAttribute("disabled") ||
                  el.getAttribute("aria-disabled") === "true" ||
                  cls.includes("disabled") ||
                  parentCls.includes("disabled") ||
                  tdCls.includes("disabled") ||
                  cls.includes("outside-month") ||
                  cls.includes("outside") ||
                  parentCls.includes("outside") ||
                  tdCls.includes("outside") ||
                  cls.includes("muted")
                );
              };
              const ariaMatchesTarget = (el) => {
                const aria = (el.getAttribute("aria-label") || "").toLowerCase();
                if (!aria) return true; // not all implementations expose aria-label
                if (monthName && !aria.includes(monthName.toLowerCase())) return false;
                if (year && !aria.includes(year)) return false;
                const dayRegex = new RegExp(`\\\\b${wanted}(st|nd|rd|th)?\\\\b`);
                return dayRegex.test(aria);
              };

              const nodes = Array.from(
                root.querySelectorAll(
                  "button, [role='gridcell']"
                )
              );

              const candidates = nodes.filter((el) => {
                const text = (el.textContent || "").trim();
                if (text !== wanted) return false;
                if (!isVisible(el) || isDisabled(el)) return false;
                if (!ariaMatchesTarget(el)) return false;
                const tag = el.tagName.toLowerCase();
                const role = (el.getAttribute("role") || "").toLowerCase();
                const cls = (el.className || "").toString().toLowerCase();
                const looksLikeDay =
                  cls.includes("day") ||
                  role === "gridcell" ||
                  tag === "button" ||
                  tag === "td";
                return looksLikeDay;
              });

              if (candidates.length === 0) return false;

              // Prefer elements explicitly marked as selected-month day cells.
              candidates.sort((a, b) => {
                const score = (el) => {
                  const cls = (el.className || "").toString().toLowerCase();
                  let s = 0;
                  if (cls.includes("react-datepicker__day")) s += 5;
                  if (cls.includes("rdp-day")) s += 5;
                  if (!cls.includes("outside") && !cls.includes("disabled")) s += 3;
                  if (el.tagName.toLowerCase() === "button") s += 2;
                  return s;
                };
                return score(b) - score(a);
              });

              candidates[0].click();
              return true;
            }
            """,
            {"day": day, "monthName": month_name, "year": str(year)},
        ))

        if clicked and (self._wait_for_continue_enabled(timeout_ms=1200) or self._is_day_marked_selected(calendar, day, month, year)):
            self.log(f"Day selected: {day:02d}")
            return

        raise RuntimeError(f"Could not click day {day:02d} in the datepicker.")

    def authenticate_and_navigate(self):
        self.log("Navigating to diary platform...")
        self.page.goto(self.config["DIARY_URL"])
        self.page.wait_for_timeout(2000) 
        
        if "sign-in" in self.page.url:
            self.log("Logging in...")
            
            email_locator = self.page.locator(
                "input[type='email'], input[name='email'], input[name='username'], input[placeholder*='mail'], input[placeholder*='sername']"
            ).first
            password_locator = self.page.locator(
                "input[type='password'], input[name='password'], input[placeholder*='assword']"
            ).first
            
            email_locator.wait_for(state="visible", timeout=15000)
            email_locator.fill(self.config["EMAIL"])
            password_locator.fill(self.config["PASSWORD"])
            password_locator.press("Enter") 
            
            self.log("Waiting for dashboard to load...")
            self.page.wait_for_url("**/dashboard**", timeout=20000)
            
            self.context.storage_state(path=str(self.config["STATE_FILE"]))
            self.log("Browser state saved.")
            
            self.page.goto(self.config["DIARY_URL"])
            self.page.wait_for_load_state("networkidle")

    def open_diary_page(self):
        """Navigates to the diary selection page for a fresh entry."""
        self.page.goto(self.config["DIARY_URL"])
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(500)

    def fill_initial_selection(self, target_date: str):
        self.log(f"Selecting internship and setting date: {target_date}")
        self.page.wait_for_selector("text='Select Internship'", timeout=10000)
        
        dropdown = self.page.get_by_text("Choose internship", exact=True)
        dropdown.click()
        self.page.wait_for_timeout(500) 
        
        self.page.keyboard.press("ArrowDown")
        self.page.keyboard.press("Enter")
        
        date_box = self.page.get_by_placeholder("Pick a Date")
        if not date_box.is_visible():
            date_box = self.page.get_by_text("Pick a Date")

        date_box.click()
        self.page.wait_for_timeout(400)

        day, month, year = self._parse_target_date(target_date)

        calendar = self._find_datepicker_root()
        calendar.wait_for(state="visible", timeout=5000)

        self.log(f"Selecting month/year from datepicker: {month:02d}/{year}")
        self._select_datepicker_month(calendar, month)
        self._select_datepicker_year(calendar, year)
        self._click_datepicker_day(calendar, day, month, year)

        if not self._wait_for_continue_enabled(timeout_ms=3000):
            self.log("Continue is still disabled after first day click. Retrying day selection once...")
            self._click_datepicker_day(calendar, day, month, year)

        if not self._wait_for_continue_enabled(timeout_ms=3000):
            current_value = self._read_date_input_value()
            shown_value = current_value if current_value else "<empty>"
            raise RuntimeError(
                f"Date was clicked but form did not accept it. "
                f"Requested {target_date}, date input value={shown_value}. "
                "This date may be outside allowed internship range."
            )
            
        self.page.wait_for_timeout(500)
        self.page.locator("button:has-text('Continue')").first.click(timeout=5000)
        self.page.wait_for_timeout(1000)

    def fill_and_submit_diary(self, data: Dict[str, Any]):
        """Fills the main diary textareas and inputs."""
        self.log("Filling out the diary form...")
        self.page.wait_for_selector("textarea[placeholder*='Briefly describe']")
        
        self.page.fill("textarea[placeholder*='Briefly describe']", data['work_summary'])
        self.page.fill("input[placeholder*='e.g. 6.5']", data['hours'])
        self.page.fill("textarea[placeholder*='What did you learn']", data['learnings'])
        self.page.fill("textarea[placeholder*='slowed you down']", data['blockers'])
        
        self.log("Adding skills via React-Select...")
        
        # Click the container to focus the invisible input
        skills_container = self.page.locator("text='Add skills'").first
        skills_container.click(force=True)

        for skill in data['skills']:
            self.log(f"Typing skill: {skill}")
            
            # Type the skill as a human would
            self.page.keyboard.type(skill, delay=50) 
            self.page.wait_for_timeout(800) 
            
            try:
                # Look for the exact match and click it
                exact_option = self.page.get_by_text(skill, exact=True).last
                exact_option.click(timeout=2000)
            except Exception:
                self.log(f"Warning: Exact match for '{skill}' not found. Backspacing...")
                # Safely backspace the exact number of characters typed
                for _ in range(len(skill)):
                    self.page.keyboard.press("Backspace")
                self.page.wait_for_timeout(200)
            
            self.page.wait_for_timeout(200) 

    def wait_for_user_to_save(self, check_cli_callback: Callable[[], bool] = lambda: False):
        self.log("Review your entry. Click 'Save' in the browser OR press 'y' here in the CLI.")
        try:
            # Inject the event listener ONCE that sets a window variable when clicked
            self.page.evaluate("""
                window.__save_clicked = false;
                document.body.addEventListener('click', (e) => {
                    let target = e.target;
                    while(target && target !== document.body) {
                        if (target.tagName === 'BUTTON' && target.textContent && target.textContent.includes('Save')) {
                            window.__save_clicked = true;
                        }
                        target = target.parentElement;
                    }
                });
            """)
            
            # Poll for either the window flag OR the CLI flag
            while True:
                if self.page.evaluate("window.__save_clicked"):
                    self.log("Browser 'Save' detected! Waiting 3s for submission...")
                    self.page.wait_for_timeout(3000)
                    break
                
                if check_cli_callback():
                    self.log("CLI 'y' detected! Clicking the browser 'Save' button automatically...")
                    try:
                        self.page.click("button:has-text('Save')", timeout=2000)
                        self.page.wait_for_timeout(3000)
                    except Exception as e:
                        self.log(f"Could not click save automatically: {e}")
                    break
                    
                self.page.wait_for_timeout(200)

        except Exception as e:
            self.log(f"Waiting for save interrupted: {e}")

    def click_save_button(self, timeout_ms: int = 15000):
        """Clicks Save button automatically and waits briefly for submit to complete."""
        save_button = self.page.locator("button:has-text('Save')").first
        save_button.wait_for(state="visible", timeout=timeout_ms)
        save_button.click(timeout=timeout_ms)
        self.page.wait_for_timeout(3000)
        self.log("Auto-save completed.")

    def capture_screenshot(self, output_path: Path):
        """Captures a screenshot of current browser page to assist debugging."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(output_path), full_page=True)
        self.log(f"Failure screenshot saved: {output_path}")

    def close(self):
        self.browser.close()
