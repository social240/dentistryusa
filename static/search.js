// DentistryUSA search (home page). Loads /search.json the first time someone
// types, then matches every word of the query against the dentist's name,
// city and specialty. Words people type map to the specialty names in the data
// ("orthodontist", "braces", "root canal", "kids dentist" ...). A 5-digit word
// matches the ZIP code and a 10-digit word the NPI number. /?q=... runs a
// search on load; the small search box in the header of other pages uses it.
(function () {
  var form = document.getElementById('search'), q = document.getElementById('q'), out = document.getElementById('results');
  if (!form || !q || !out) return;
  var data = null, loading = false, MAX = 20;

  // What people type -> what the data calls it.
  var SYN = [
    [/\b(pediatric dent\w*|paediatric dent\w*|pedodont\w*|kids?|childrens?|child|pediatric)\b/g, 'pediatric dentistry'],
    [/\b(orthodont\w*|ortho|braces|invisalign|aligners?)\b/g, 'orthodontics'],
    [/\b(oral and maxillofacial surg\w*|oral surg\w*|maxillofacial surg\w*|wisdom teeth|tooth extractions?|extractions?)\b/g, 'oral and maxillofacial surgery'],
    [/\b(endodont\w*|root canals?|endo)\b/g, 'endodontics'],
    [/\b(periodont\w*|perio|gums?)\b/g, 'periodontics'],
    [/\b(prosthodont\w*|prostho|dentures?)\b/g, 'prosthodontics'],
    [/\b(general dentists?|general dentistry|family dentists?|family dentistry)\b/g, 'general practice']
  ];
  // Words that do not narrow a dentist search.
  var STOP = {dentist: 1, dentists: 1, dental: 1, dentistry: 1, dr: 1, doctor: 1, doctors: 1, near: 1, me: 1, in: 1,
              at: 1, fl: 1, florida: 1, the: 1, a: 1, an: 1, for: 1, of: 1, best: 1, top: 1, office: 1, clinic: 1};

  // Same text rules for the query and the data: lower case, letters and digits
  // only, and one spelling of saint/fort/mount (the data has both).
  function norm(s) {
    return (' ' + s.toLowerCase().replace(/[^a-z0-9]+/g, ' ') + ' ')
      .replace(/ saint /g, ' st ').replace(/ fort /g, ' ft ').replace(/ mount /g, ' mt ')
      .replace(/\s+/g, ' ').trim();
  }
  function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  // The query as a list of tests, each one a function of an entry.
  function terms(raw) {
    var t = norm(raw), phrases = [];
    SYN.forEach(function (p) {
      t = t.replace(p[0], function () { phrases.push(p[1]); return ' zzphrase' + (phrases.length - 1) + 'zz '; });
    });
    var words = t.split(' ').filter(Boolean), keep = words.filter(function (w) { return !STOP[w]; });
    if (!keep.length) keep = words;           // "dentist" alone still searches
    return keep.map(function (w) {
      var m = /^zzphrase(\d+)zz$/.exec(w);
      if (m) { var ph = phrases[+m[1]]; return function (d) { return d.hay.indexOf(ph) > -1; }; }
      if (/^\d{5}$/.test(w)) return function (d) { return d.zip === w; };
      if (/^\d{10}$/.test(w)) return function (d) { return d.npi === w; };
      return function (d) { return d.hay.indexOf(w) > -1; };
    });
  }

  function show(h) { out.innerHTML = h; out.hidden = !h; }
  function run() {
    var raw = q.value.trim();
    if (raw.length < 2) { show(''); return; }
    var tests = terms(raw), hits = [], total = 0;
    for (var i = 0; i < data.length; i++) {
      var d = data[i], ok = true;
      for (var j = 0; j < tests.length && ok; j++) ok = tests[j](d);
      if (ok) { total++; if (hits.length < MAX) hits.push(d); }
    }
    if (!total) { show('<li class="none">No matches. Try a city, a ZIP code, a specialty or a last name.</li>'); return; }
    var html = hits.map(function (d) {
      return '<li><a href="' + d.url + '"><strong>' + esc(d.name) + '</strong><span>' + esc(d.spec) + ' · ' +
        esc(d.city) + ', FL ' + esc(d.zip) + '</span></a></li>';
    }).join('');
    if (total > MAX) html += '<li class="none">Showing ' + MAX + ' of ' + total.toLocaleString('en-US') + ' matches. Add a word to narrow it down.</li>';
    show(html);
  }

  // search.json: {cities:[...], specs:[...], rows:[[npi, "First Last", credential, city#, specialty#, zip], ...]}
  function load(j) {
    data = j.rows.map(function (r) {
      var city = j.cities[r[3]], spec = j.specs[r[4]];
      return {npi: r[0], zip: r[5], city: city, spec: spec,
              name: 'Dr. ' + r[1] + (r[2] ? ', ' + r[2] : ''),
              url: '/dentist/' + r[0] + '-' + slug(r[1]) + '/',
              hay: norm(r[1] + ' ' + city + ' ' + spec)};
    });
  }
  function go() {
    if (data) return run();
    if (loading) return;
    loading = true;
    if (q.value.trim().length >= 2) show('<li class="none">Searching…</li>');
    fetch('/search.json').then(function (r) { return r.json(); }).then(function (j) { load(j); run(); })
      .catch(function () { loading = false; show('<li class="none">Search is unavailable right now. Please try again.</li>'); });
  }
  q.addEventListener('input', go);
  q.addEventListener('focus', function () { if (out.innerHTML) out.hidden = false; });
  form.addEventListener('submit', function (e) { e.preventDefault(); go(); });
  document.addEventListener('click', function (e) { if (!form.contains(e.target)) out.hidden = true; });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') out.hidden = true; });
  var p = new URLSearchParams(location.search).get('q');
  if (p) { q.value = p; go(); }
})();
