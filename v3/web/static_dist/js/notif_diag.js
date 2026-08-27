(()=>{function t(e){return String(e??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}function m(){return document.getElementById("ndRoot")}function u(e){let s=document.getElementById("ndMsg");s&&(s.textContent=e,s.hidden=!e)}async function g(e,s=!1){let c=m(),a=document.getElementById("ndOut");if(!c||!a||!e)return;let p=(c.getAttribute(s?"data-run-url":"data-url")||"").replace("__EMAIL__",encodeURIComponent(e)),i=await fetch(p,{method:s?"POST":"GET",headers:s?{"X-CSRF-Token":c.getAttribute("data-csrf")||"",Accept:"application/json"}:{Accept:"application/json"}}),n=await i.json().catch(()=>({}));if(!i.ok){u(n.error||"Could not load diagnostic.");return}u(s?`Generated ${n.generated??0} overdue alerts (all users).`:"");let r=n.user||{},l=n.would_create||[],d=n.would_skip||[];a.innerHTML=`
    <section class="settings-card">
      <p><strong>${t(r.email||"")}</strong> \xB7 ${t(r.role||"")} \xB7 active ${r.is_active?"yes":"no"} \xB7 dashboard ${r.dashboard_enabled?"on":"off"}</p>
      <p class="flag-desc">Mirror refreshed ${t(String(n.last_refreshed||"never"))} \xB7 ${t(String(n.matched_customers||0))} customers in scope \xB7 ${t(String(n.overdue_in_scope||0))} overdue</p>
      <h3 class="settings-subhead">Would create (${l.length})</h3>
      <ul>${l.map(o=>`<li>${t(o.customer_account)} \u2014 ${t(o.customer_name)}</li>`).join("")||"<li>None</li>"}</ul>
      <h3 class="settings-subhead">Would skip (${d.length})</h3>
      <ul>${d.map(o=>`<li>${t(o.customer_account)} \u2014 ${t(o.reason)}</li>`).join("")||"<li>None</li>"}</ul>
      <h3 class="settings-subhead">Excluded</h3>
      <p>${(n.excluded||[]).map(o=>t(o)).join(", ")||"None"}</p>
      <h3 class="settings-subhead">Active alerts</h3>
      <p>${(n.active_notifications||[]).length}</p>
    </section>`}document.addEventListener("DOMContentLoaded",()=>{let e=document.getElementById("ndUser");e?.addEventListener("change",()=>{e.value&&g(e.value)}),document.getElementById("ndRun")?.addEventListener("click",()=>{e?.value&&g(e.value,!0)})});})();
//# sourceMappingURL=notif_diag.js.map
