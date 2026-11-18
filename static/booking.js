// DentistryUSA online booking, in the usual doctor-booking pattern:
//   * profile pages (#book): reason for the visit, new or returning patient, a week
//     of open times, then the patient's details. No account needed.
//   * /appointment/#<token> (#appt): the patient's own appointment, opened from the
//     private link shown after booking. View, move or cancel it.
// The database functions (booking_slots, book_appointment, get_appointment,
// reschedule_appointment, cancel_appointment) check everything again; the checks
// here only give quicker, clearer errors.
(function () {
  var C = window.DUSA || {};
  // Keep in step with private.visit_reasons() in supabase/migrations/001_booking.sql.
  var REASONS = ['Checkup and cleaning', 'Tooth pain', 'Dental emergency', 'Filling or crown',
                 'Tooth extraction', 'Braces or aligners consultation', 'Cosmetic consultation', 'Other'];
  var TZ_NAME = {'America/New_York': 'Eastern Time', 'America/Chicago': 'Central Time'};
  var SHOW = 6;   // times shown per day before "Show more times"

  function rpc(fn, args) {
    return fetch(C.url + '/rest/v1/rpc/' + fn, {
      method: 'POST', headers: {apikey: C.key, 'Content-Type': 'application/json'}, body: JSON.stringify(args || {})
    }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (j) {
        if (!r.ok) {
          var e = new Error(j && j.message ? j.message : 'Something went wrong. Please try again.');
          e.hint = j && j.hint;
          throw e;
        }
        return j;
      });
    }, function () { throw new Error('We could not reach DentistryUSA. Check your connection and try again.'); });
  }

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
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }

  // ---------------------------------------------------------------- dates and times
  var fmts = {};
  function fmt(tz, opts) {
    var k = tz + JSON.stringify(opts);
    if (!fmts[k]) { var o = {timeZone: tz}; Object.keys(opts).forEach(function (x) { o[x] = opts[x]; }); fmts[k] = new Intl.DateTimeFormat('en-US', o); }
    return fmts[k];
  }
  // The calendar day of an instant in a time zone, as YYYY-MM-DD.
  function dayKey(date, tz) {
    var p = {};
    fmt(tz, {year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(date).forEach(function (x) { p[x.type] = x.value; });
    return p.year + '-' + p.month + '-' + p.day;
  }
  function timeText(iso, tz) { return fmt(tz, {hour: 'numeric', minute: '2-digit'}).format(new Date(iso)); }
  function dateText(iso, tz) { return fmt(tz, {weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'}).format(new Date(iso)); }
  function whenText(iso, tz) { return dateText(iso, tz) + ' at ' + timeText(iso, tz); }
  function shortWhen(iso, tz) { return fmt(tz, {weekday: 'short', month: 'short', day: 'numeric'}).format(new Date(iso)) + ' at ' + timeText(iso, tz); }
  function tzName(tz) { return TZ_NAME[tz] || tz; }
  function phoneText(p) { var d = String(p || '').replace(/\D/g, ''); return d.length === 10 ? '(' + d.slice(0, 3) + ') ' + d.slice(3, 6) + '-' + d.slice(6) : p; }

  // Every calendar day from today, in the practice's time zone, for days_ahead days
  // (the same days the database offers times on).
  function dayList(tz, ahead) {
    var k = dayKey(new Date(), tz).split('-').map(Number), out = [];
    for (var i = 0; i <= ahead; i++) {
      var d = new Date(Date.UTC(k[0], k[1] - 1, k[2] + i, 12));
      out.push({key: dayKey(d, 'UTC'), wd: fmt('UTC', {weekday: 'short'}).format(d),
                md: fmt('UTC', {month: 'short', day: 'numeric'}).format(d),
                long: fmt('UTC', {weekday: 'long', month: 'long', day: 'numeric'}).format(d)});
    }
    return out;
  }

  // ---------------------------------------------------------------- add to calendar (.ics)
  function icsDate(d) { return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, ''); }
  function icsText(s) { return String(s).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n'); }
  function icsFold(line) {
    var out = [];
    while (line.length > 73) { out.push(line.slice(0, 73)); line = ' ' + line.slice(73); }
    out.push(line);
    return out.join('\r\n');
  }
  function saveIcs(a) {
    var start = new Date(a.starts_at), end = new Date(start.getTime() + a.minutes * 60000);
    var lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//DentistryUSA//Booking//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
      'BEGIN:VEVENT', 'UID:' + a.token + '@dentistryusa.com', 'DTSTAMP:' + icsDate(new Date()),
      'DTSTART:' + icsDate(start), 'DTEND:' + icsDate(end),
      'SUMMARY:' + icsText('Dentist appointment: ' + a.dentist),
      a.address ? 'LOCATION:' + icsText(a.address) : '',
      'DESCRIPTION:' + icsText('Reason: ' + a.reason + (a.phone ? '\nOffice phone: ' + phoneText(a.phone) : '') +
                               '\nChange or cancel: ' + a.link),
      'END:VEVENT', 'END:VCALENDAR'].filter(Boolean).map(icsFold);
    var url = URL.createObjectURL(new Blob([lines.join('\r\n') + '\r\n'], {type: 'text/calendar;charset=utf-8'}));
    var link = h('a', {href: url, download: 'dentist-appointment.ics'});
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }
  function manageLink(token) { return location.origin + '/appointment/#' + token; }

  // ---------------------------------------------------------------- the week of open times
  // data: what booking_slots returns. onPick(iso) runs when a time is chosen.
  function picker(box, data, onPick) {
    var tz = data.timezone, days = dayList(tz, data.days_ahead || 28), byDay = {}, weeks = [], w = 0, more = false, chosen = null;
    data.slots.forEach(function (iso) { var k = dayKey(new Date(iso), tz); (byDay[k] = byDay[k] || []).push(iso); });
    for (var i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
    var label = h('p', {'aria-live': 'polite'});
    var prev = h('button', {type: 'button', class: 'wk', 'aria-label': 'Previous week', text: '\u2039', on: {click: function () { go(w - 1); }}});
    var next = h('button', {type: 'button', class: 'wk', 'aria-label': 'Next week', text: '\u203a', on: {click: function () { go(w + 1); }}});
    var grid = h('ul', {class: 'week'}), foot = h('div', {class: 'wkfoot'});
    clear(box).appendChild(h('div', {class: 'wkbar'}, [prev, label, next]));
    box.appendChild(grid);
    box.appendChild(foot);
    box.appendChild(h('p', {class: 'muted', text: 'Times are in ' + tzName(tz) + '.'}));

    function go(n) { w = Math.max(0, Math.min(weeks.length - 1, n)); more = false; render(); }
    function render() {
      var week = weeks[w], many = false;
      label.textContent = week[0].md + ' \u2013 ' + week[week.length - 1].md;
      prev.disabled = w === 0;
      next.disabled = w === weeks.length - 1;
      clear(grid);
      week.forEach(function (d) {
        var list = byDay[d.key] || [];
        if (list.length > SHOW) many = true;
        var shown = more ? list : list.slice(0, SHOW);
        grid.appendChild(h('li', {class: 'day'}, [
          h('p', {class: 'dname'}, [h('b', {text: d.wd}), d.md]),
          list.length ? h('ul', {class: 'times'}, shown.map(function (iso) {
            return h('li', {}, [h('button', {type: 'button', class: 'slot', 'aria-pressed': iso === chosen ? 'true' : 'false',
              'aria-label': d.long + ', ' + timeText(iso, tz), text: timeText(iso, tz),
              on: {click: function () { chosen = iso; render(); onPick(iso); }}})]);
          })) : h('p', {class: 'none'}, [h('span', {'aria-hidden': 'true', text: '\u2013'}), h('span', {class: 'sr', text: 'No open times'})])
        ]));
      });
      clear(foot);
      var open = week.some(function (d) { return byDay[d.key]; });
      if (!open) {
        var later = null;
        for (var j = w + 1; j < weeks.length && !later; j++) {
          weeks[j].forEach(function (d) { if (!later && byDay[d.key]) later = {week: j, day: d}; });
        }
        foot.appendChild(h('p', {}, ['No open times this week. ', later ? h('button', {type: 'button', class: 'linkish',
          text: 'Next available: ' + later.day.wd + ', ' + later.day.md, on: {click: function () { go(later.week); }}}) : null]));
      } else if (many) {
        foot.appendChild(h('button', {type: 'button', class: 'linkish', text: more ? 'Show fewer times' : 'Show more times',
          on: {click: function () { more = !more; render(); }}}));
      }
    }
    render();
  }

  // ---------------------------------------------------------------- profile page: book
  function field(id, label, input, hint) {
    input.id = id;
    var kids = [h('label', {for: id}, [label]), input];
    if (hint) { kids.push(hint); input.setAttribute('aria-describedby', hint.id); }
    return h('p', {}, kids);
  }
  function radios(name, legend, opts) {
    return h('fieldset', {}, [h('legend', {text: legend})].concat(opts.map(function (o) {
      return h('label', {class: 'opt'}, [h('input', {type: 'radio', name: name, value: o[0], checked: !!o[2]}), ' ' + o[1]]);
    })));
  }
  function picked(root, name) { var r = root.querySelector('input[name=' + name + ']:checked'); return r ? r.value : ''; }

  // MM/DD/YYYY to YYYY-MM-DD, or '' if it is not a real date of birth.
  function dobIso(s) {
    var m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s.trim());
    if (!m) return '';
    var y = +m[3], mo = +m[1], d = +m[2], t = new Date(Date.UTC(y, mo - 1, d));
    if (t.getUTCFullYear() !== y || t.getUTCMonth() !== mo - 1 || t.getUTCDate() !== d) return '';
    if (y < 1900 || t > new Date()) return '';
    return y + '-' + ('0' + mo).slice(-2) + '-' + ('0' + d).slice(-2);
  }

  function bookBox(sec) {
    var npi = sec.getAttribute('data-npi'), aside = document.getElementById('claimBox');
    var info = {dentist: sec.getAttribute('data-dentist'), address: sec.getAttribute('data-address'), phone: sec.getAttribute('data-phone')};
    rpc('booking_slots', {p_npi: npi}).then(function (data) {
      if (!data) return;
      if (data.claimed && aside) managedAside(aside, data);
      if (!data.enabled) return;
      sec.hidden = false;
      buildBox(sec, npi, info, data);
    }).catch(function () { /* the profile works without booking */ });
  }

  function managedAside(aside, data) {
    clear(aside);
    if (data.enabled) {
      aside.appendChild(h('p', {}, [h('strong', {text: 'Book online'})]));
      aside.appendChild(h('p', {}, data.slots.length
        ? ['Next available: ', h('strong', {text: shortWhen(data.slots[0], data.timezone)})]
        : ['No open times online right now. Please call the office.']));
      if (data.slots.length) aside.appendChild(h('a', {class: 'btn', href: '#book', text: 'See open times'}));
    } else {
      aside.appendChild(h('p', {text: 'This listing is managed by the practice.'}));
    }
    aside.appendChild(h('p', {class: 'muted'}, ['Are you the dentist? ', h('a', {href: '/account/', text: 'Sign in'}), '.']));
  }

  function buildBox(sec, npi, info, data) {
    var tz = data.timezone, chosen = null;
    var reason = h('select', {required: true}, [h('option', {value: '', text: 'Choose a reason'})].concat(
      REASONS.map(function (r) { return h('option', {value: r, text: r}); })));
    var questions = h('div', {class: 'bk-q'}, [
      field('b-reason', 'Reason for your visit', reason),
      radios('b-ptype', 'Have you visited this dentist before?', [['new', 'No, I am a new patient'], ['existing', 'Yes, I have been here before']])
    ]);
    var times = h('div', {class: 'bk-times'});
    var whenH = h('h3', {tabindex: '-1'});
    var first = h('input', {autocomplete: 'given-name', maxlength: '60', required: true});
    var last = h('input', {autocomplete: 'family-name', maxlength: '60', required: true});
    var dob = h('input', {inputmode: 'numeric', autocomplete: 'bday', placeholder: 'MM/DD/YYYY', maxlength: '10', required: true});
    var phone = h('input', {type: 'tel', autocomplete: 'tel-national', maxlength: '20', required: true});
    var email = h('input', {type: 'email', autocomplete: 'email', maxlength: '254', required: true});
    var note = h('textarea', {rows: '2', maxlength: '100'});
    var count = h('span', {class: 'hint', id: 'b-count', text: '0 of 100 characters'});
    var err = h('p', {class: 'err', role: 'alert', tabindex: '-1', hidden: true});
    var submit = h('button', {class: 'btn', type: 'submit', text: 'Book appointment'});
    var firstL = h('label', {for: 'b-first', text: 'First name'}), lastL = h('label', {for: 'b-last', text: 'Last name'});
    var dobL = h('label', {for: 'b-dob', text: 'Date of birth'});
    first.id = 'b-first'; last.id = 'b-last'; dob.id = 'b-dob';
    var form = h('form', {class: 'bk-form', novalidate: true, hidden: true}, [
      whenH,
      radios('b-for', 'Who is this appointment for?', [['self', 'Me', true], ['someone_else', 'Someone else']]),
      h('div', {class: 'two'}, [h('p', {}, [firstL, first]), h('p', {}, [lastL, last])]),
      h('p', {}, [dobL, dob]),
      h('div', {class: 'two'}, [field('b-phone', 'Mobile phone', phone), field('b-email', 'Email', email)]),
      field('b-note', h('span', {}, ['Note for the office ', h('span', {class: 'opt-label', text: '(optional)'})]), note, count),
      err, submit,
      h('p', {class: 'muted', text: 'For a medical emergency, call 911.'})
    ]);
    var done = h('div', {class: 'card done', tabindex: '-1', hidden: true});

    clear(sec);
    [h('h2', {id: 'bookH', text: 'Book an appointment'}),
     h('p', {class: 'muted', text: 'Pick a time that works for you. No account needed.'}),
     questions, h('h3', {text: 'Choose a time'}), times, form, done].forEach(function (n) { sec.appendChild(n); });

    // msg: an error to show above the times (after a time was taken by someone else).
    function showTimes(d, msg) {
      if (!d.slots.length) {
        clear(times).appendChild(h('p', {}, ['No open times online right now. Please call the office' +
          (info.phone ? ' at ' + phoneText(info.phone) : '') + '.']));
        form.hidden = true;
      } else {
        picker(times, d, function (iso) {
          chosen = iso;
          whenH.textContent = whenText(iso, tz) + ' (' + tzName(tz) + ')';
          form.hidden = false;
          setErr('');
          whenH.focus();
        });
      }
      if (msg) {
        var m = h('p', {class: 'err', role: 'alert', tabindex: '-1', text: msg});
        times.insertBefore(m, times.firstChild);
        m.focus();
      }
    }
    showTimes(data);

    function setErr(msg, focusEl) {
      err.textContent = msg || '';
      err.hidden = !msg;
      if (msg) (focusEl || err).focus();
    }
    Array.prototype.forEach.call(form.querySelectorAll('input[name=b-for]'), function (r) {
      r.addEventListener('change', function () {
        var other = picked(form, 'b-for') === 'someone_else';
        firstL.textContent = other ? 'Patient\u2019s first name' : 'First name';
        lastL.textContent = other ? 'Patient\u2019s last name' : 'Last name';
        dobL.textContent = other ? 'Patient\u2019s date of birth' : 'Date of birth';
      });
    });
    dob.addEventListener('input', function (e) {
      if (e.inputType && e.inputType.indexOf('delete') === 0) return;
      var d = dob.value.replace(/\D/g, '').slice(0, 8);
      dob.value = d.length > 4 ? d.slice(0, 2) + '/' + d.slice(2, 4) + '/' + d.slice(4) : d.length > 2 ? d.slice(0, 2) + '/' + d.slice(2) : d;
    });
    note.addEventListener('input', function () { count.textContent = note.value.length + ' of 100 characters'; });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      setErr('');
      var f = {reason: reason.value, ptype: picked(sec, 'b-ptype'), who: picked(form, 'b-for') || 'self',
               first: first.value.trim(), last: last.value.trim(), dob: dobIso(dob.value),
               phone: phone.value.replace(/\D/g, ''), email: email.value.trim(), note: note.value.trim()};
      if (f.phone.length === 11 && f.phone[0] === '1') f.phone = f.phone.slice(1);
      if (!chosen) return setErr('Please choose a time.');
      if (!f.reason) return setErr('Please choose a reason for the visit.', reason);
      if (!f.ptype) return setErr('Please say whether you have visited this dentist before.', sec.querySelector('input[name=b-ptype]'));
      if (!f.first || !f.last) return setErr('Please enter the patient\u2019s first and last name.', f.first ? last : first);
      if (!f.dob) return setErr('Please enter a valid date of birth, like 04/27/1985.', dob);
      if (!/^[2-9]\d{2}[2-9]\d{6}$/.test(f.phone)) return setErr('Please enter a 10-digit US phone number.', phone);
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) return setErr('Please enter a valid email address.', email);
      if (f.note.length > 100) return setErr('The note can be up to 100 characters.', note);
      submit.disabled = true;
      submit.textContent = 'Booking\u2026';
      rpc('book_appointment', {p_npi: npi, p_starts_at: chosen, p_reason: f.reason, p_patient_type: f.ptype,
                               p_first_name: f.first, p_last_name: f.last, p_dob: f.dob, p_phone: f.phone,
                               p_email: f.email, p_booked_for: f.who, p_note: f.note})
        .then(function (res) { booked(res, f); })
        .catch(function (er) {
          submit.disabled = false;
          submit.textContent = 'Book appointment';
          if (er.hint === 'slot_unavailable') {
            chosen = null;
            form.hidden = true;
            rpc('booking_slots', {p_npi: npi})
              .then(function (d) { showTimes(d && d.enabled ? d : {slots: []}, er.message); })
              .catch(function () { showTimes({slots: []}, er.message); });
            return;
          }
          setErr(er.message);
        });
    });

    function booked(res, f) {
      var link = manageLink(res.token);
      var appt = {token: res.token, starts_at: res.starts_at, minutes: res.minutes, dentist: info.dentist,
                  address: info.address, phone: info.phone, reason: f.reason, link: link};
      var linkBox = h('input', {id: 'b-link', readonly: true, value: link});
      var copy = h('button', {type: 'button', class: 'btn ghost', text: 'Copy', on: {click: function () {
        linkBox.select();
        (navigator.clipboard ? navigator.clipboard.writeText(link) : Promise.reject()).then(function () { copy.textContent = 'Copied'; },
          function () { document.execCommand && document.execCommand('copy'); copy.textContent = 'Copied'; });
      }}});
      clear(done);
      [h('h3', {text: 'You\u2019re booked'}),
       h('p', {}, [h('strong', {text: whenText(res.starts_at, res.timezone)}), h('br'),
                   tzName(res.timezone) + ' \u00b7 ' + res.minutes + ' minutes \u00b7 ' + f.reason]),
       h('p', {}, [info.dentist].concat(info.address ? [h('br'), info.address] : []).concat(info.phone ? [h('br'), phoneText(info.phone)] : [])),
       h('p', {class: 'actions'}, [h('a', {class: 'btn', href: link, text: 'View, change or cancel'}),
         h('button', {type: 'button', class: 'btn ghost', text: 'Add to calendar', on: {click: function () { saveIcs(appt); }}})]),
       h('p', {}, [h('label', {for: 'b-link', text: 'Save this link. You need it to change or cancel online.'}),
                   h('span', {class: 'copyrow'}, [linkBox, copy])]),
       h('p', {class: 'muted', text: 'To change it another way, call the office' + (info.phone ? ' at ' + phoneText(info.phone) : '') + '.'})
      ].forEach(function (n) { done.appendChild(n); });
      questions.hidden = true;
      times.hidden = true;
      form.hidden = true;
      sec.querySelector('h3').hidden = true;
      done.hidden = false;
      done.focus();
    }
  }

  // ---------------------------------------------------------------- /appointment/: view, move, cancel
  function apptPage(root) {
    var token = '';
    try { token = decodeURIComponent(location.hash.replace(/^#/, '')).trim(); } catch (e) { token = ''; }
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(token)) {
      return notFound();
    }
    load('');

    function notFound() {
      clear(root).appendChild(h('div', {class: 'card'}, [h('h2', {text: 'We could not find this appointment'}),
        h('p', {text: 'Please open the full link you saved when you booked. To change an appointment another way, call the dental office.'})]));
    }
    function load(msg) {
      rpc('get_appointment', {p_token: token}).then(function (a) {
        if (!a) return notFound();
        show(a, msg);
      }).catch(function (e) {
        clear(root).appendChild(h('p', {class: 'err', role: 'alert', text: e.message}));
      });
    }
    function show(a, msg) {
      var tz = a.timezone, past = new Date(a.starts_at) <= new Date();
      var cancelled = a.status === 'cancelled';
      var status = cancelled ? 'Cancelled' : past ? 'Past' : 'Booked';
      var appt = {token: token, starts_at: a.starts_at, minutes: a.minutes, dentist: a.dentist, address: a.address,
                  phone: a.phone, reason: a.reason, link: manageLink(token)};
      var note = msg ? h('p', {class: 'ok', role: 'status', tabindex: '-1', text: msg}) : null;
      var resched = h('div', {class: 'card', hidden: true});
      var card = h('div', {class: 'card'}, [
        h('div', {class: 'inbox-head'}, [h('h2', {text: whenText(a.starts_at, tz)}),
          h('span', {class: 'badge ' + (cancelled ? 'cancelled' : 'booked'), text: status})]),
        h('p', {class: 'muted', text: tzName(tz) + ' \u00b7 ' + a.minutes + ' minutes'}),
        h('dl', {class: 'facts'}, [
          h('dt', {text: 'Dentist'}), h('dd', {}, [h('a', {href: a.url, text: a.dentist})]),
          a.address ? h('dt', {text: 'Address'}) : null, a.address ? h('dd', {text: a.address}) : null,
          a.phone ? h('dt', {text: 'Office phone'}) : null,
          a.phone ? h('dd', {}, [h('a', {href: 'tel:+1' + a.phone.replace(/\D/g, ''), text: phoneText(a.phone)})]) : null,
          h('dt', {text: 'Patient'}), h('dd', {text: a.first_name}),
          h('dt', {text: 'Reason'}), h('dd', {text: a.reason + ' \u00b7 ' + (a.patient_type === 'new' ? 'New patient' : 'Returning patient')})
        ]),
        cancelled ? h('p', {}, ['This appointment was cancelled' + (a.cancelled_by === 'practice' ? ' by the office' : '') + '. ',
                                h('a', {href: a.url, text: 'Book another time'}), '.'])
          : past ? h('p', {class: 'muted', text: 'This appointment has passed.'})
          : a.can_change ? h('p', {class: 'actions'}, [
              h('button', {type: 'button', class: 'btn', text: 'Change time', on: {click: function () { openResched(); }}}),
              h('button', {type: 'button', class: 'btn ghost', text: 'Cancel appointment', on: {click: cancel}}),
              h('button', {type: 'button', class: 'btn ghost', text: 'Add to calendar', on: {click: function () { saveIcs(appt); }}})])
          : null
      ]);
      clear(root);
      [note, card, resched].forEach(function (n) { if (n) root.appendChild(n); });
      if (note) note.focus();

      function cancel(e) {
        if (!confirm('Cancel your appointment on ' + whenText(a.starts_at, tz) + '?')) return;
        e.target.disabled = true;
        rpc('cancel_appointment', {p_token: token}).then(function (res) { show(res, 'Your appointment is cancelled.'); })
          .catch(function (er) { e.target.disabled = false; alert(er.message); });
      }

      // msg: an error to show first (after the picked time was taken by someone else).
      function openResched(msg) {
        var chosen = null, err = h('p', {class: 'err', role: 'alert', tabindex: '-1', hidden: !msg, text: msg || ''});
        var move = h('button', {type: 'button', class: 'btn', disabled: true, text: 'Pick a new time'});
        var keep = h('button', {type: 'button', class: 'linkish', text: 'Keep my current time', on: {click: function () { resched.hidden = true; }}});
        var times = h('div', {class: 'bk-times'}, [h('p', {class: 'muted', text: 'Loading open times\u2026'})]);
        var title = h('h2', {tabindex: '-1', text: 'Pick a new time'});
        clear(resched);
        [title, err, times, h('p', {class: 'actions'}, [move, keep])].forEach(function (n) { resched.appendChild(n); });
        resched.hidden = false;
        (msg ? err : title).focus();
        rpc('booking_slots', {p_npi: a.npi}).then(function (d) {
          if (!d || !d.enabled || !d.slots.length) {
            clear(times).appendChild(h('p', {text: 'Online changes are not available right now. Please call the office' +
              (a.phone ? ' at ' + phoneText(a.phone) : '') + '.'}));
            return;
          }
          picker(times, d, function (iso) {
            chosen = iso;
            err.hidden = true;
            move.disabled = false;
            move.textContent = 'Move to ' + shortWhen(iso, d.timezone);
            move.focus();
          });
        }).catch(function (er) { clear(times).appendChild(h('p', {class: 'err', text: er.message})); });
        move.addEventListener('click', function () {
          if (!chosen) return;
          move.disabled = true;
          rpc('reschedule_appointment', {p_token: token, p_new_start: chosen})
            .then(function (res) { show(res, 'Your appointment is moved to ' + whenText(res.starts_at, res.timezone) + '.'); })
            .catch(function (er) {
              if (er.hint === 'slot_unavailable') return openResched(er.message);
              err.textContent = er.message;
              err.hidden = false;
              err.focus();
              move.disabled = false;
            });
        });
      }
    }
  }

  var sec = document.getElementById('book');
  if (sec && C.url) bookBox(sec);
  var appt = document.getElementById('appt');
  if (appt && C.url) {
    apptPage(appt);
    window.addEventListener('hashchange', function () { apptPage(appt); });
  }
})();
