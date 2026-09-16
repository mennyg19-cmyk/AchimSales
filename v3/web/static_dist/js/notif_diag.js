(()=>{function m(){return document.getElementById("ndRoot")}function l(e){let n=document.getElementById("ndMsg");n&&(n.textContent=e,n.hidden=!e)}async function u(e,n=!1){let a=m(),c=document.getElementById("ndOut");if(!a||!c||!e)return;let g=(a.getAttribute(n?"data-run-url":"data-url")||"").replace("__EMAIL__",encodeURIComponent(e)),r=await fetch(g,{method:n?"POST":"GET",headers:n?{"X-CSRF-Token":a.getAttribute("data-csrf")||"",Accept:"application/json"}:{Accept:"application/json"}}),t=await r.json().catch(()=>({}));if(!r.ok){l(t.error||"Could not load diagnostic.");return}l(n?`Generated ${t.generated??0} overdue alerts (all users).`:"");let o=t.user||{},d=t.would_create||[],i=t.would_skip||[];c.innerHTML=`
    <section class="settings-card">
      <p><strong>${o.email||""}</strong> \xB7 ${o.role||""} \xB7 active ${o.is_active?"yes":"no"} \xB7 dashboard ${o.dashboard_enabled?"on":"off"}</p>
      <p class="flag-desc">Mirror refreshed ${t.last_refreshed||"never"} \xB7 ${t.matched_customers||0} customers in scope \xB7 ${t.overdue_in_scope||0} overdue</p>
      <h3 class="settings-subhead">Would create (${d.length})</h3>
      <ul>${d.map(s=>`<li>${s.customer_account} \u2014 ${s.customer_name}</li>`).join("")||"<li>None</li>"}</ul>
      <h3 class="settings-subhead">Would skip (${i.length})</h3>
      <ul>${i.map(s=>`<li>${s.customer_account} \u2014 ${s.reason}</li>`).join("")||"<li>None</li>"}</ul>
      <h3 class="settings-subhead">Excluded</h3>
      <p>${(t.excluded||[]).join(", ")||"None"}</p>
      <h3 class="settings-subhead">Active alerts</h3>
      <p>${(t.active_notifications||[]).length}</p>
    </section>`}document.addEventListener("DOMContentLoaded",()=>{let e=document.getElementById("ndUser");e?.addEventListener("change",()=>{e.value&&u(e.value)}),document.getElementById("ndRun")?.addEventListener("click",()=>{e?.value&&u(e.value,!0)})});})();
//# sourceMappingURL=notif_diag.js.map
