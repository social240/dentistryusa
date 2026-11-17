// DentistryUSA admin inbox (/admin/): claims and removal requests.
// Sign-in is an emailed magic link. Only users in public.admins see anything;
// the database checks that on every call, not this page.
(function () {
  var C = window.DUSA || {}, root = document.getElementById('admin');
  if (!root || !window.supabase) return;
  var sb = window.supabase.createClient(C.url, C.key, {auth: {persistSession: true, detectSessionInUrl: true}});

  // Small DOM builder; text always goes in as text, never as HTML.
  function h(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') n.textContent = attrs[k];
      else if (k === 'on') Object.keys(attrs.on).forEach(function (ev) { n.addEventListener(ev, attrs.on[ev]); });
      else n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function when(iso) {
    return new Date(iso).toLocaleString('en-US', {month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit'});
  }
  function mail(addr) { return h('a', {href: 'mailto:' + addr, text: addr}); }
  function set(kids) { root.textContent = ''; kids.forEach(function (k) { if (k) root.appendChild(k); }); }
  function fail(msg) { return h('p', {class: 'err', role: 'alert', text: msg}); }

  function signIn(note) {
    var email = h('input', {id: 'aemail', type: 'email', autocomplete: 'email', required: ''});
    var msg = h('p', {class: 'muted', 'aria-live': 'polite'});
    var btn = h('button', {class: 'btn', type: 'submit', text: 'Email me a sign-in link'});
    var form = h('form', {class: 'card formcard', on: {submit: function (e) {
      e.preventDefault();
      btn.disabled = true;
      msg.textContent = 'Sending…';
      sb.auth.signInWithOtp({email: email.value.trim(), options: {emailRedirectTo: location.origin + '/admin/'}})
        .then(function (r) {
          btn.disabled = false;
          msg.textContent = r.error ? r.error.message : 'Check your email for a sign-in link. It expires in 1 hour.';
        });
    }}}, [h('h2', {text: 'Admin sign-in'}), note ? fail(note) : null,
          h('p', {}, [h('label', {for: 'aemail', text: 'Email'}), email]), btn, msg]);
    set([form]);
  }

  function bar(session) {
    return h('p', {class: 'muted adminbar'}, ['Signed in as ' + session.user.email + ' · ',
      h('button', {type: 'button', class: 'linkish', text: 'Sign out', on: {click: function () { sb.auth.signOut().then(function () { signIn(); }); }}})]);
  }

  function act(fn, args, button) {
    button.disabled = true;
    return sb.rpc(fn, args).then(function (r) {
      if (r.error) { button.disabled = false; alert(r.error.message); return; }
      load();
    });
  }

  function claimCard(c) {
    var pending = c.status === 'pending';
    return h('li', {class: 'inbox-item'}, [
      h('div', {class: 'inbox-head'}, [h('a', {href: c.url, text: c.dentist}), h('span', {class: 'badge ' + c.status, text: c.status})]),
      h('p', {class: 'muted', text: 'NPI ' + c.npi + ' · ' + c.city + ', FL · sent ' + when(c.created_at)}),
      h('p', {}, [h('strong', {text: c.full_name}), ' (' + c.role + ') · ', mail(c.email), c.phone ? ' · ' + c.phone : '']),
      h('p', {class: 'actions'}, pending ? [
        h('button', {class: 'btn', type: 'button', text: 'Approve', on: {click: function (e) { act('review_claim', {p_id: c.id, p_approve: true}, e.target); }}}),
        h('button', {class: 'btn ghost', type: 'button', text: 'Reject', on: {click: function (e) { act('review_claim', {p_id: c.id, p_approve: false}, e.target); }}})
      ] : c.status === 'approved' ? [
        h('button', {class: 'btn ghost', type: 'button', text: 'Revoke', on: {click: function (e) {
          if (confirm('Take this listing away from ' + c.full_name + '?')) act('review_claim', {p_id: c.id, p_approve: false}, e.target); }}})
      ] : [])
    ]);
  }

  function removalCard(r) {
    var label = r.request === 'remove_listing' ? 'Remove listing' : 'Stop emails';
    return h('li', {class: 'inbox-item'}, [
      h('div', {class: 'inbox-head'}, [h('strong', {text: label}), h('span', {class: 'badge ' + r.status, text: r.status})]),
      r.npi ? h('p', {class: 'muted'}, [r.dentist ? h('a', {href: r.url, text: r.dentist}) : 'Unknown listing',
        ' · NPI ' + r.npi + (r.city ? ' · ' + r.city + ', FL' : '')]) : null,
      h('p', {}, [h('strong', {text: r.full_name}), ' · ', mail(r.email), ' · sent ' + when(r.created_at)]),
      r.note ? h('p', {class: 'note', text: r.note}) : null,
      r.status === 'new' ? h('p', {class: 'actions'}, [h('button', {class: 'btn', type: 'button', text: 'Mark done',
        on: {click: function (e) { act('close_removal', {p_id: r.id}, e.target); }}})]) : null
    ]);
  }

  function section(title, items, empty, make, hint) {
    return h('section', {class: 'inbox'}, [h('h2', {text: title}), hint ? h('p', {class: 'muted', text: hint}) : null,
      items.length ? h('ul', {class: 'inbox-list'}, items.map(make)) : h('p', {class: 'muted', text: empty})]);
  }

  function load() {
    sb.auth.getSession().then(function (s) {
      var session = s.data.session;
      if (!session) return signIn();
      sb.rpc('is_admin').then(function (a) {
        if (a.error || !a.data) {
          return set([bar(session), fail('This account is not an admin. Ask to be added, then reload this page.')]);
        }
        sb.rpc('admin_inbox').then(function (r) {
          if (r.error) return set([bar(session), fail(r.error.message)]);
          var claims = r.data.claims, removals = r.data.removals;
          var openClaims = claims.filter(function (c) { return c.status === 'pending'; }).length;
          var openRemovals = removals.filter(function (x) { return x.status === 'new'; }).length;
          set([bar(session),
            section('Claims (' + openClaims + ' waiting)', claims, 'No claims yet.', claimCard,
              'Approving a claim makes that email the owner of the listing.'),
            section('Removal requests (' + openRemovals + ' new)', removals, 'No removal requests yet.', removalCard,
              'To take a listing off the site, add its NPI to data/removed.txt in the repo and push. Then mark the request done.')]);
        });
      });
    });
  }

  sb.auth.onAuthStateChange(function (ev) { if (ev === 'SIGNED_IN') load(); });
  load();
})();
