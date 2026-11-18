// DentistryUSA dentist account (/account/). Sign-in is an emailed link. A dentist
// sees a listing here once an admin has approved their claim and they sign in with
// the same email. They turn online booking on or off, set their weekly hours, and
// see and cancel appointments. The database (my_account, save_practice,
// dentist_cancel) decides what each person owns; this page only shows it.
(function () {
  var C = window.DUSA || {}, root = document.getElementById('account');
  if (!root || !window.supabase) return;
  var sb = window.supabase.createClient(C.url, C.key, {auth: {persistSession: true, detectSessionInUrl: true}});
  var DAYS = [[1, 'Monday'], [2, 'Tuesday'], [3, 'Wednesday'], [4, 'Thursday'], [5, 'Friday'], [6, 'Saturday'], [0, 'Sunday']];
  var TZ_NAME = {'America/New_York': 'Eastern Time', 'America/Chicago': 'Central Time'};
  // The user whose account is on screen, and whether a load is running: a sign-in
  // event during either must not redraw the page and wipe unsaved edits.
  var shownFor = null, loading = false;

  // Small DOM builder; text always goes in as text, never as HTML.
  function h(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'text') n.textContent = v;
      else if (k === 'on') Object.keys(v).forEach(function (ev) { n.addEventListener(ev, v[ev]); });
      else n.setAttribute(k, v === true ? '' : v);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function set(kids) { root.textContent = ''; kids.forEach(function (k) { if (k) root.appendChild(k); }); }
  function fail(msg) { return h('p', {class: 'err', role: 'alert', tabindex: '-1', text: msg}); }
  function when(iso, tz) {
    return new Intl.DateTimeFormat('en-US', {timeZone: tz, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}).format(new Date(iso));
  }
  function phoneText(p) { var d = String(p || '').replace(/\D/g, ''); return d.length === 10 ? '(' + d.slice(0, 3) + ') ' + d.slice(3, 6) + '-' + d.slice(6) : p; }
  function dobText(d) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || ''); return m ? m[2] + '/' + m[3] + '/' + m[1] : d; }
  function select(id, value, opts) {
    var s = h('select', {id: id}, opts.map(function (o) { return h('option', {value: String(o[0]), text: o[1]}); }));
    if (!opts.some(function (o) { return String(o[0]) === String(value); })) s.appendChild(h('option', {value: String(value), text: String(value)}));
    s.value = String(value);
    return s;
  }

  function signIn(note) {
    var email = h('input', {id: 'demail', type: 'email', autocomplete: 'email', required: true});
    var msg = h('p', {class: 'muted', 'aria-live': 'polite'});
    var btn = h('button', {class: 'btn', type: 'submit', text: 'Email me a sign-in link'});
    var form = h('form', {class: 'card formcard', on: {submit: function (e) {
      e.preventDefault();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim())) { msg.textContent = 'Please enter a valid email address.'; return; }
      btn.disabled = true;
      msg.textContent = 'Sending…';
      sb.auth.signInWithOtp({email: email.value.trim(), options: {emailRedirectTo: location.origin + '/account/'}})
        .then(function (r) {
          btn.disabled = false;
          msg.textContent = r.error ? r.error.message : 'Check your email for a sign-in link. It expires in 1 hour.';
        });
    }}}, [h('h2', {text: 'Dentist sign-in'}), note ? fail(note) : null,
          h('p', {text: 'Use the email on your approved claim. We will email you a link to sign in. No password needed.'}),
          h('p', {}, [h('label', {for: 'demail', text: 'Email'}), email]), btn, msg,
          h('p', {class: 'muted'}, ['Not claimed yet? ', h('a', {href: '/claim/', text: 'Claim your free listing'}), '.'])]);
    set([form]);
  }

  function bar(session) {
    return h('p', {class: 'muted adminbar'}, ['Signed in as ' + session.user.email + ' · ',
      h('button', {type: 'button', class: 'linkish', text: 'Sign out', on: {click: function () { sb.auth.signOut().then(function () { signIn(); }); }}})]);
  }

  // msg: a note to show at the top after a save or a cancel.
  function load(msg) {
    loading = true;
    sb.auth.getSession().then(function (s) {
      var session = s.data.session;
      if (!session) { loading = false; return signIn(); }
      sb.rpc('my_account').then(function (r) {
        loading = false;
        shownFor = session.user.id;
        if (r.error) return set([bar(session), fail(r.error.message)]);
        var acc = r.data, kids = [bar(session)], top = null;
        if (msg) { top = h('p', {class: 'ok', role: 'status', tabindex: '-1', text: msg}); kids.push(top); }
        acc.pending.forEach(function (c) {
          kids.push(h('div', {class: 'card'}, [h('p', {}, ['Your claim for ', h('a', {href: c.url, text: c.dentist}), ' in ' + c.city +
            ', FL is waiting for review. You can set up online booking here once it is approved.'])]));
        });
        if (!acc.listings.length && !acc.pending.length) {
          kids.push(h('div', {class: 'card'}, [h('h2', {text: 'No listing yet'}),
            h('p', {text: 'There is no approved listing for ' + acc.email + '. If you claimed your listing with another email, sign out and sign in with that one.'}),
            h('p', {}, [h('a', {class: 'btn', href: '/claim/', text: 'Claim your free listing'})])]));
        }
        acc.listings.forEach(function (l) { kids.push(listing(l)); });
        set(kids);
        if (top) top.focus();
      });
    });
  }

  function listing(l) {
    var name = l.dentist + (l.credential ? ', ' + l.credential : '');
    return h('section', {class: 'card listing'}, [
      h('div', {class: 'inbox-head'}, [h('h2', {text: name}),
        h('span', {class: 'badge ' + (l.booking_enabled ? 'on' : 'off'), text: l.booking_enabled ? 'Online booking on' : 'Online booking off'})]),
      h('p', {class: 'muted'}, [l.specialty + ' · ' + l.city + ', FL · NPI ' + l.npi + ' · ', h('a', {href: l.url, text: 'View your profile'})]),
      h('h3', {text: 'Appointments'}),
      appointments(l),
      h('h3', {text: 'Online booking'}),
      settings(l)
    ]);
  }

  function appointments(l) {
    var tz = l.timezone, list = l.appointments;
    if (!list.length) return h('p', {class: 'muted', text: l.booking_enabled ? 'No appointments yet.' : 'No appointments. Turn on online booking below to take them.'});
    return h('ul', {class: 'inbox-list'}, list.map(function (a) {
      var cancelled = a.status === 'cancelled', future = new Date(a.starts_at) > new Date();
      var who = a.first_name + ' ' + a.last_name;
      var tag = cancelled ? (a.cancelled_by === 'practice' ? 'Cancelled by you' : 'Cancelled by the patient') : future ? 'Booked' : 'Past';
      return h('li', {class: 'inbox-item' + (cancelled ? ' off' : '')}, [
        h('div', {class: 'inbox-head'}, [h('span', {text: when(a.starts_at, tz) + ' · ' + a.minutes + ' min'}),
          h('span', {class: 'badge ' + (cancelled ? 'cancelled' : 'booked'), text: tag})]),
        h('p', {}, [h('strong', {text: who}), ' · born ' + dobText(a.date_of_birth) + ' · ' +
          (a.patient_type === 'new' ? 'New patient' : 'Returning patient') + (a.booked_for === 'someone_else' ? ' · booked by someone else' : '')]),
        h('p', {text: 'Reason: ' + a.reason}),
        h('p', {}, [h('a', {href: 'tel:+1' + a.phone, text: phoneText(a.phone)}), ' · ', h('a', {href: 'mailto:' + a.email, text: a.email})]),
        a.note ? h('p', {class: 'note', text: a.note}) : null,
        !cancelled && future ? h('p', {class: 'actions'}, [h('button', {type: 'button', class: 'btn ghost', text: 'Cancel appointment', on: {click: function (e) {
          if (!confirm('Cancel ' + who + '’s appointment on ' + when(a.starts_at, tz) + '?\n\nThe patient is not told automatically. Please call or email them.')) return;
          e.target.disabled = true;
          sb.rpc('dentist_cancel', {p_id: a.id}).then(function (r) {
            if (r.error || !r.data) { e.target.disabled = false; alert(r.error ? r.error.message : 'This appointment can no longer be cancelled.'); return; }
            load('Cancelled ' + who + '’s appointment. Please let them know.');
          });
        }}})]) : null
      ]);
    }));
  }

  function settings(l) {
    var id = function (s) { return s + '-' + l.npi; };
    var enabled = h('input', {type: 'checkbox', id: id('on'), checked: l.booking_enabled});
    var slot = select(id('slot'), l.slot_minutes, [[15, '15 minutes'], [20, '20 minutes'], [30, '30 minutes'], [45, '45 minutes'], [60, '1 hour']]);
    var notice = select(id('notice'), l.min_notice_hours, [[0, 'No notice'], [1, '1 hour'], [2, '2 hours'], [4, '4 hours'], [12, '12 hours'], [24, '1 day'], [48, '2 days'], [72, '3 days']]);
    var ahead = select(id('ahead'), l.days_ahead, [[7, '1 week'], [14, '2 weeks'], [21, '3 weeks'], [28, '4 weeks'], [42, '6 weeks'], [60, '60 days']]);
    var tz = select(id('tz'), l.timezone, [['America/New_York', 'Eastern Time'], ['America/Chicago', 'Central Time (western Panhandle)']]);
    var err = h('p', {class: 'err', role: 'alert', tabindex: '-1', hidden: true});
    var btn = h('button', {class: 'btn', type: 'submit', text: 'Save'});
    var hours = hoursEditor(l);
    tz.addEventListener('change', function () { hours.querySelector('legend').textContent = 'Opening hours (' + (TZ_NAME[tz.value] || tz.value) + ')'; });
    var form = h('form', {class: 'bkset', novalidate: true}, [
      h('label', {class: 'opt', for: id('on')}, [enabled, ' Let patients book online on my profile']),
      h('div', {class: 'setgrid'}, [
        h('p', {}, [h('label', {for: id('slot'), text: 'Appointment length'}), slot]),
        h('p', {}, [h('label', {for: id('notice'), text: 'Notice you need before a visit'}), notice]),
        h('p', {}, [h('label', {for: id('ahead'), text: 'How far ahead patients can book'}), ahead]),
        h('p', {}, [h('label', {for: id('tz'), text: 'Time zone'}), tz])]),
      hours, err, btn]);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      err.hidden = true;
      var got = collectHours(form);
      var bad = got.error || (enabled.checked && !got.hours.length ? 'Add your opening hours before you turn on online booking.' : '');
      if (bad) { err.textContent = bad; err.hidden = false; err.focus(); return; }
      btn.disabled = true;
      btn.textContent = 'Saving…';
      sb.rpc('save_practice', {p_npi: l.npi, p_enabled: enabled.checked, p_slot_minutes: +slot.value, p_min_notice_hours: +notice.value,
                               p_days_ahead: +ahead.value, p_timezone: tz.value, p_hours: got.hours})
        .then(function (r) {
          if (r.error) { btn.disabled = false; btn.textContent = 'Save'; err.textContent = r.error.message; err.hidden = false; err.focus(); return; }
          load(enabled.checked ? 'Saved. Patients can now book online on your profile.' : 'Saved. Online booking is off.');
        });
    });
    return form;
  }

  // One row per weekday: open or closed, and one or more time ranges.
  function hoursEditor(l) {
    var byDay = {}, fresh = !l.hours.length;
    l.hours.forEach(function (x) { (byDay[x.weekday] = byDay[x.weekday] || []).push(x); });
    return h('fieldset', {class: 'hours'}, [h('legend', {text: 'Opening hours (' + (TZ_NAME[l.timezone] || l.timezone) + ')'}),
      h('p', {class: 'hint', text: 'Patients can book times inside these hours. Add a second range for a lunch break.' +
        (fresh ? ' Monday to Friday, 9 to 5 is filled in to start; nothing is saved until you press Save.' : '')})]
      .concat(DAYS.map(function (d) {
        return dayRow(l.npi, d[0], d[1], byDay[d[0]] || (fresh && d[0] >= 1 && d[0] <= 5 ? [{start: '09:00', end: '17:00'}] : []));
      })));
  }

  function dayRow(npi, wd, name, ranges) {
    var box = h('input', {type: 'checkbox', checked: ranges.length > 0});
    var list = h('div', {class: 'ranges'});
    var add = h('button', {type: 'button', class: 'linkish add', text: 'Add hours', on: {click: function () { addRange('', ''); }}});
    function addRange(s, e) {
      var start = h('input', {type: 'time', step: '900', value: s, 'aria-label': name + ' opens'});
      var end = h('input', {type: 'time', step: '900', value: e, 'aria-label': name + ' closes'});
      var row = h('span', {class: 'range'}, [start, h('span', {class: 'to', text: 'to'}), end]);
      row.appendChild(h('button', {type: 'button', class: 'linkish', text: 'Remove', 'aria-label': 'Remove these ' + name + ' hours', on: {click: function () {
        row.remove();
        if (!list.children.length) { box.checked = false; sync(); }
      }}}));
      list.appendChild(row);
      if (!s) start.focus();
    }
    function sync() {
      list.hidden = add.hidden = !box.checked;
      if (box.checked && !list.children.length) addRange('09:00', '17:00');
    }
    box.addEventListener('change', sync);
    ranges.forEach(function (r) { addRange(r.start, r.end); });
    sync();
    return h('div', {class: 'hrow', 'data-wd': String(wd)}, [h('label', {class: 'opt'}, [box, ' ' + name]), list, add]);
  }

  function collectHours(form) {
    var out = [], bad = '';
    Array.prototype.forEach.call(form.querySelectorAll('.hrow'), function (row) {
      if (!row.querySelector('input[type=checkbox]').checked) return;
      var wd = +row.getAttribute('data-wd');
      Array.prototype.forEach.call(row.querySelectorAll('.range'), function (r) {
        var t = r.querySelectorAll('input[type=time]'), s = t[0].value, e = t[1].value;
        if (!s || !e) { bad = bad || 'Fill in both times for each range of hours, or remove it.'; return; }
        if (e <= s) { bad = bad || 'Each closing time must be after the opening time.'; return; }
        out.push({weekday: wd, start: s, end: e});
      });
    });
    return {hours: out, error: bad};
  }

  // setTimeout: supabase-js asks not to call the client from inside this callback.
  sb.auth.onAuthStateChange(function (ev, session) {
    if (ev === 'SIGNED_IN' && session && session.user.id !== shownFor && !loading) setTimeout(load, 0);
    if (ev === 'SIGNED_OUT') { shownFor = null; setTimeout(signIn, 0); }
  });
  load();
})();
