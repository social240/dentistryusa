// Dentist lists: mark the listings that take online bookings, with their next open
// time (database function online_listings). The list works the same without it.
(function () {
  var C = window.DUSA || {}, docs = document.querySelectorAll('.doc[data-npi]');
  if (!docs.length || !C.url) return;
  var KEY = 'dusa-online', cached = null;
  try {
    var c = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (c && Date.now() - c.t < 5 * 60 * 1000) cached = c.v;
  } catch (e) { /* storage blocked: just ask the database */ }
  function when(iso, tz) {
    return new Intl.DateTimeFormat('en-US', {timeZone: tz, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'})
      .format(new Date(iso));
  }
  (cached ? Promise.resolve(cached)
    : fetch(C.url + '/rest/v1/rpc/online_listings', {method: 'POST', headers: {apikey: C.key, 'Content-Type': 'application/json'}, body: '{}'})
        .then(function (r) { return r.ok ? r.json() : []; })
        .then(function (v) {
          try { sessionStorage.setItem(KEY, JSON.stringify({t: Date.now(), v: v})); } catch (e) { /* fine */ }
          return v;
        }))
    .then(function (list) {
      var by = {};
      (list || []).forEach(function (x) { by[x.npi] = x; });
      Array.prototype.forEach.call(docs, function (li) {
        var x = by[li.getAttribute('data-npi')];
        if (!x) return;
        var p = document.createElement('p');
        p.className = 'bookonline';
        p.textContent = x.next ? 'Book online · Next: ' + when(x.next, x.timezone) : 'Books online';
        (li.querySelector('div') || li).appendChild(p);
      });
    })
    .catch(function () { /* the list works without it */ });
})();
