// DentistryUSA forms: /claim/ and /remove/. Both send straight to the database
// functions submit_claim and submit_removal (no account needed). The database
// checks everything again, so these checks only give quicker, clearer errors.
(function () {
  var C = window.DUSA || {};
  var SUPPORT = 'support@dentistryusa.com';

  function rpc(fn, args) {
    return fetch(C.url + '/rest/v1/rpc/' + fn, {
      method: 'POST', headers: {apikey: C.key, 'Content-Type': 'application/json'}, body: JSON.stringify(args)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j && j.message ? j.message : 'Something went wrong. Please try again.');
        return j;
      });
    }, function () { throw new Error('We could not reach DentistryUSA. Check your connection and try again.'); });
  }
  function listing(npi) {
    return fetch(C.url + '/rest/v1/dentists?select=name,credential,city,url&npi=eq.' + npi, {headers: {apikey: C.key}})
      .then(function (r) { return r.ok ? r.json() : []; }).then(function (a) { return a[0] || null; })
      .catch(function () { return null; });
  }
  function $(form, sel) { return form.querySelector(sel); }
  function setErr(form, msg) {
    var e = $(form, '.err');
    e.textContent = msg || '';
    e.hidden = !msg;
    if (msg) e.focus();
  }
  function text(tag, s, cls) { var n = document.createElement(tag); n.textContent = s; if (cls) n.className = cls; return n; }

  // The NPI field: digits only, exactly 10, and it shows which listing it is.
  function npiField(form, required) {
    var input = $(form, '#npi'), info = $(form, '#npiInfo'), last = '';
    var pre = new URLSearchParams(location.search).get('npi');
    if (pre && /^\d{10}$/.test(pre)) input.value = pre;
    function check() {
      var v = input.value.replace(/\D/g, '');
      if (v !== input.value) input.value = v;
      if (v === last) return;
      last = v;
      info.textContent = '';
      input.removeAttribute('aria-invalid');
      if (v.length === 10) {
        listing(v).then(function (d) {
          if (input.value !== v) return;
          if (d) { info.textContent = 'Listing: ' + d.name + (d.credential ? ', ' + d.credential : '') + ' in ' + d.city + ', FL'; }
          else { info.textContent = 'We could not find this NPI number in our Florida listings.'; input.setAttribute('aria-invalid', 'true'); }
        });
      }
    }
    input.addEventListener('input', check);
    check();
    return function validate() {
      var v = input.value;
      if (!v && !required()) return '';
      if (!/^\d{10}$/.test(v)) { input.setAttribute('aria-invalid', 'true'); input.focus(); return 'The NPI number must be exactly 10 digits.'; }
      return '';
    };
  }

  function done(form, panelId, title, lines) {
    var panel = document.getElementById(panelId);
    panel.textContent = '';
    panel.appendChild(text('h2', title));
    lines.forEach(function (l) { panel.appendChild(l); });
    form.hidden = true;
    panel.hidden = false;
    panel.focus();
  }
  function supportLine(prefix) {
    var p = text('p', prefix + ' ', 'muted'), a = document.createElement('a');
    a.href = 'mailto:' + SUPPORT;
    a.textContent = SUPPORT;
    p.appendChild(a);
    p.appendChild(document.createTextNode('.'));
    return p;
  }
  function busy(form, on) {
    var b = $(form, 'button[type=submit]');
    b.disabled = on;
    b.textContent = on ? 'Sending…' : b.getAttribute('data-label');
  }

  // /claim/
  var claim = document.getElementById('claim');
  if (claim) {
    var claimNpi = npiField(claim, function () { return true; });
    $(claim, 'button[type=submit]').setAttribute('data-label', $(claim, 'button[type=submit]').textContent);
    claim.addEventListener('submit', function (e) {
      e.preventDefault();
      setErr(claim, '');
      var bad = claimNpi();
      if (bad) return setErr(claim, bad);
      var f = {npi: $(claim, '#npi').value, name: $(claim, '#name').value.trim(), email: $(claim, '#email').value.trim(),
               phone: $(claim, '#phone').value.trim(), role: $(claim, '#role').value};
      if (f.name.length < 2) return setErr(claim, 'Please enter your name.');
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) return setErr(claim, 'Please enter a valid work email.');
      busy(claim, true);
      Promise.all([rpc('submit_claim', {p_npi: f.npi, p_full_name: f.name, p_email: f.email, p_role: f.role, p_phone: f.phone}),
                   listing(f.npi)])
        .then(function (res) {
          var d = res[1], who = d ? d.name + (d.credential ? ', ' + d.credential : '') + ' in ' + d.city + ', FL' : 'NPI ' + f.npi;
          var next = text('p', 'We will review it and contact you at ');
          next.appendChild(text('strong', f.email));
          next.appendChild(document.createTextNode('. Claiming is free.'));
          done(claim, 'claimDone', 'Thanks, we got your claim.', [text('p', 'Listing: ' + who + ' (NPI ' + f.npi + ').'), next,
            supportLine('Questions? Email')]);
        })
        .catch(function (err) { busy(claim, false); setErr(claim, err.message); });
    });
  }

  // /remove/
  var removal = document.getElementById('remove');
  if (removal) {
    var wantsRemoval = function () { return $(removal, 'input[name=request]:checked').value === 'remove_listing'; };
    var removalNpi = npiField(removal, wantsRemoval);
    var opt = $(removal, '#npiOpt');
    var syncReq = function () { opt.hidden = wantsRemoval(); };
    Array.prototype.forEach.call(removal.querySelectorAll('input[name=request]'), function (r) { r.addEventListener('change', syncReq); });
    var want = new URLSearchParams(location.search).get('request');
    if (want === 'stop_emails') $(removal, 'input[value=stop_emails]').checked = true;
    syncReq();
    $(removal, 'button[type=submit]').setAttribute('data-label', $(removal, 'button[type=submit]').textContent);
    removal.addEventListener('submit', function (e) {
      e.preventDefault();
      setErr(removal, '');
      var bad = removalNpi();
      if (bad) return setErr(removal, bad);
      var f = {npi: $(removal, '#npi').value, req: $(removal, 'input[name=request]:checked').value,
               name: $(removal, '#name').value.trim(), email: $(removal, '#email').value.trim(), note: $(removal, '#note').value.trim()};
      if (f.name.length < 2) return setErr(removal, 'Please enter your name.');
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) return setErr(removal, 'Please enter a valid email address.');
      busy(removal, true);
      rpc('submit_removal', {p_npi: f.npi, p_request: f.req, p_full_name: f.name, p_email: f.email, p_note: f.note})
        .then(function () {
          var what = f.req === 'remove_listing'
            ? 'We will remove the listing for NPI ' + f.npi + ' from DentistryUSA.'
            : 'We will stop sending emails to ' + f.email + '.';
          done(removal, 'removeDone', 'Thanks, we got your request.', [text('p', what), supportLine('Questions? Email')]);
        })
        .catch(function (err) { busy(removal, false); setErr(removal, err.message); });
    });
  }
})();
