-- DentistryUSA: listings, claims, booking settings, weekly hours and appointments.
--
-- Run once on a new Supabase project (SQL editor, or the Management API), then
-- load the listings with supabase/load_dentists.py.
--
-- The booking flow follows the usual doctor-booking pattern (as on Zocdoc):
-- the patient picks a visit reason and new/existing, sees open times a week at
-- a time, picks one, gives name, date of birth, phone and email, and gets a
-- private link to view, move or cancel the appointment.
--
-- How access works:
--   * Every table has row level security, and anon/authenticated get only the
--     grants listed here (this project's defaults would otherwise expose
--     every new table).
--   * Patients never read tables. They see open times and book, move or
--     cancel through the functions at the bottom; an appointment is found only
--     by its secret token.
--   * Anyone can send a claim or a removal request (no account needed); both
--     wait in the admin inbox. A dentist owns a listing once an admin approves
--     their claim, and signs in with the email on that claim (a magic link
--     proves the address). Owners set hours and see their own appointments.
--     Admins are the users in public.admins.

create extension if not exists btree_gist with schema extensions;

-- Server-only settings and helpers (not reachable through the API).
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table if not exists private.config (name text primary key, value text not null);
insert into private.config (name, value) values ('ip_salt', gen_random_uuid()::text)
on conflict (name) do nothing;

-- A salted hash of the caller's IP, for rate limits (the raw IP is never stored).
create or replace function private.client_ip_hash() returns text
language plpgsql stable set search_path = '' as $$
declare
  v_hdr json := nullif(current_setting('request.headers', true), '')::json;
  v_ip  text := nullif(btrim(coalesce(v_hdr ->> 'cf-connecting-ip', v_hdr ->> 'x-real-ip',
                                      split_part(v_hdr ->> 'x-forwarded-for', ',', 1))), '');
begin
  if v_ip is null then
    return null;
  end if;
  return encode(sha256(convert_to(v_ip || ':' || (select c.value from private.config c where c.name = 'ip_salt'), 'UTF8')), 'hex');
end $$;

-- The visit reasons a patient can pick. Keep in step with REASONS in static/booking.js.
create or replace function private.visit_reasons() returns text[]
language sql immutable set search_path = '' as $$
  select array['Checkup and cleaning', 'Tooth pain', 'Dental emergency', 'Filling or crown',
               'Tooth extraction', 'Braces or aligners consultation', 'Cosmetic consultation', 'Other']
$$;

-- ---------------------------------------------------------------- tables

create table public.dentists (
  npi        text primary key check (npi ~ '^[0-9]{10}$'),
  name       text not null,
  credential text not null default '',
  specialty  text not null,
  city       text not null,
  address    text not null default '',
  phone      text not null default '',
  url        text not null
);
comment on table public.dentists is 'The public listing, loaded from data/fl-dentists-seed.csv (NPI registry).';

create table public.admins (
  user_id uuid primary key references auth.users (id) on delete cascade
);

create table public.claims (
  id          bigint generated always as identity primary key,
  npi         text not null references public.dentists (npi),
  full_name   text not null check (char_length(full_name) between 2 and 120),
  email       text not null check (char_length(email) <= 254 and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  phone       text not null default '' check (char_length(phone) <= 30),
  role        text not null check (role in ('Dentist', 'Office manager', 'Other')),
  status      text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  ip_hash     text,
  created_at  timestamptz not null default now(),
  reviewed_at timestamptz
);
-- One owner per listing, and one open claim per listing and email.
create unique index claims_one_owner on public.claims (npi) where status = 'approved';
create unique index claims_one_open on public.claims (npi, lower(email)) where status = 'pending';
create index claims_ip on public.claims (ip_hash, created_at);

-- "Remove my listing" and "stop emailing me" requests from /remove.
create table public.removal_requests (
  id         bigint generated always as identity primary key,
  npi        text check (npi ~ '^[0-9]{10}$'),
  request    text not null check (request in ('remove_listing', 'stop_emails')),
  full_name  text not null check (char_length(full_name) between 2 and 120),
  email      text not null check (char_length(email) <= 254 and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  note       text not null default '' check (char_length(note) <= 500),
  status     text not null default 'new' check (status in ('new', 'done')),
  ip_hash    text,
  created_at timestamptz not null default now(),
  handled_at timestamptz
);
create index removal_requests_ip on public.removal_requests (ip_hash, created_at);

create table public.practices (
  npi              text primary key references public.dentists (npi),
  booking_enabled  boolean not null default false,
  slot_minutes     int not null default 30 check (slot_minutes in (15, 20, 30, 45, 60)),
  min_notice_hours int not null default 2 check (min_notice_hours between 0 and 72),
  days_ahead       int not null default 28 check (days_ahead between 1 and 60),
  timezone         text not null default 'America/New_York'
                   check (timezone in ('America/New_York', 'America/Chicago')),
  updated_at       timestamptz not null default now()
);

create table public.weekly_hours (
  npi        text not null references public.practices (npi) on delete cascade,
  weekday    int not null check (weekday between 0 and 6),   -- 0 = Sunday
  start_time time not null,
  end_time   time not null,
  check (end_time > start_time),
  primary key (npi, weekday, start_time)
);

create table public.appointments (
  id             bigint generated always as identity primary key,
  npi            text not null references public.dentists (npi),
  starts_at      timestamptz not null,
  ends_at        timestamptz not null,
  reason         text not null check (reason = any (private.visit_reasons())),
  patient_type   text not null check (patient_type in ('new', 'existing')),
  booked_for     text not null default 'self' check (booked_for in ('self', 'someone_else')),
  first_name     text not null check (char_length(first_name) between 1 and 60),
  last_name      text not null check (char_length(last_name) between 1 and 60),
  date_of_birth  date not null check (date_of_birth >= date '1900-01-01'),
  phone          text not null check (phone ~ '^[2-9][0-9]{2}[2-9][0-9]{6}$'),   -- 10 digits, US
  email          text not null check (char_length(email) <= 254 and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  note           text not null default '' check (char_length(note) <= 100),
  status         text not null default 'booked' check (status in ('booked', 'cancelled')),
  cancelled_by   text check (cancelled_by in ('patient', 'practice')),
  cancel_token   uuid not null default gen_random_uuid() unique,
  ip_hash        text,
  created_at     timestamptz not null default now(),
  rescheduled_at timestamptz,
  cancelled_at   timestamptz,
  check (ends_at > starts_at),
  -- Two booked appointments for the same dentist can never overlap.
  constraint no_double_booking exclude using gist (npi with =, tstzrange(starts_at, ends_at) with &&)
    where (status = 'booked')
);
create index appointments_npi_starts on public.appointments (npi, starts_at);
create index appointments_email on public.appointments (lower(email));
create index appointments_ip on public.appointments (ip_hash, created_at);

create or replace function private.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;
create trigger practices_touch before update on public.practices
  for each row execute function private.touch_updated_at();

-- ---------------------------------------------------------------- helpers used by policies

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.admins a where a.user_id = (select auth.uid()))
$$;

create or replace function public.owns_npi(p_npi text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.claims c
                 where c.npi = p_npi and c.status = 'approved'
                   and lower(c.email) = lower((select auth.jwt()) ->> 'email'))
$$;

-- ---------------------------------------------------------------- row level security and grants

alter table public.dentists     enable row level security;
alter table public.admins       enable row level security;
alter table public.claims       enable row level security;
alter table public.removal_requests enable row level security;
alter table public.practices    enable row level security;
alter table public.weekly_hours enable row level security;
alter table public.appointments enable row level security;

revoke all on public.dentists, public.admins, public.claims, public.removal_requests, public.practices,
              public.weekly_hours, public.appointments from anon, authenticated;
-- removal_requests gets no grants at all: it is read and written only through functions.

grant select on public.dentists to anon, authenticated;
create policy "Listings are public" on public.dentists for select using (true);

grant select on public.claims to authenticated;
create policy "Own claims, or all for admins" on public.claims for select to authenticated
  using (lower(email) = lower((select auth.jwt()) ->> 'email') or public.is_admin());

grant select on public.practices to authenticated;
grant update (booking_enabled, slot_minutes, min_notice_hours, days_ahead, timezone) on public.practices to authenticated;
create policy "Owners and admins read settings" on public.practices for select to authenticated
  using (public.owns_npi(npi) or public.is_admin());
create policy "Owners change settings" on public.practices for update to authenticated
  using (public.owns_npi(npi)) with check (public.owns_npi(npi));

grant select on public.weekly_hours to authenticated;
create policy "Owners and admins read hours" on public.weekly_hours for select to authenticated
  using (public.owns_npi(npi) or public.is_admin());

grant select on public.appointments to authenticated;
create policy "Owners read their appointments" on public.appointments for select to authenticated
  using (public.owns_npi(npi));

-- ---------------------------------------------------------------- open times (anyone)

-- Every open start time for a listing that takes online bookings.
-- p_ignore: an appointment to leave out of the clash check (used when moving it).
create or replace function public.get_open_slots(p_npi text, p_ignore bigint default null)
returns table (starts_at timestamptz, minutes int, timezone text)
language sql stable security definer set search_path = '' as $$
  with p as (
    select pr.npi, pr.slot_minutes, pr.min_notice_hours, pr.days_ahead, pr.timezone
    from public.practices pr
    where pr.npi = p_npi and pr.booking_enabled
      and exists (select 1 from public.claims c where c.npi = pr.npi and c.status = 'approved')
  ),
  days as (
    select p.*, (now() at time zone p.timezone)::date + g as d
    from p, generate_series(0, p.days_ahead) as g
  ),
  slots as (
    select days.npi, days.slot_minutes, days.min_notice_hours, days.timezone,
           (t at time zone days.timezone) as s
    from days
    join public.weekly_hours h on h.npi = days.npi and h.weekday = extract(dow from days.d)::int
    cross join lateral generate_series(days.d + h.start_time,
                                       days.d + h.end_time - make_interval(mins => days.slot_minutes),
                                       make_interval(mins => days.slot_minutes)) as t
  )
  select sl.s, sl.slot_minutes, sl.timezone
  from slots sl
  where sl.s >= now() + make_interval(hours => sl.min_notice_hours)
    and not exists (
      select 1 from public.appointments a
      where a.npi = sl.npi and a.status = 'booked' and a.id is distinct from p_ignore
        and tstzrange(a.starts_at, a.ends_at) && tstzrange(sl.s, sl.s + make_interval(mins => sl.slot_minutes)))
  order by sl.s
$$;

-- What a profile page needs: whether the listing books online, and its open times.
create or replace function public.booking_slots(p_npi text) returns json
language sql stable security definer set search_path = '' as $$
  select json_build_object(
    'enabled', coalesce((select pr.booking_enabled
                                and exists (select 1 from public.claims c where c.npi = pr.npi and c.status = 'approved')
                         from public.practices pr where pr.npi = p_npi), false),
    'timezone', coalesce((select pr.timezone from public.practices pr where pr.npi = p_npi), 'America/New_York'),
    'minutes', (select pr.slot_minutes from public.practices pr where pr.npi = p_npi),
    'days_ahead', (select pr.days_ahead from public.practices pr where pr.npi = p_npi),
    'slots', coalesce((select json_agg(o.starts_at order by o.starts_at) from public.get_open_slots(p_npi) o), '[]'::json))
$$;

-- Every listing that books online, with its next open time (for the city and specialty lists).
create or replace function public.online_listings() returns json
language sql stable security definer set search_path = '' as $$
  select coalesce(json_agg(json_build_object(
           'npi', pr.npi, 'timezone', pr.timezone,
           'next', (select min(o.starts_at) from public.get_open_slots(pr.npi) o))), '[]'::json)
  from public.practices pr
  where pr.booking_enabled
    and exists (select 1 from public.claims c where c.npi = pr.npi and c.status = 'approved')
$$;

-- ---------------------------------------------------------------- booking (anyone)

create or replace function public.book_appointment(
  p_npi text, p_starts_at timestamptz, p_reason text, p_patient_type text,
  p_first_name text, p_last_name text, p_dob date, p_phone text, p_email text,
  p_booked_for text default 'self', p_note text default '')
returns json
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_minutes int;
  v_tz      text;
  v_id      bigint;
  v_token   uuid;
  v_first   text := btrim(coalesce(p_first_name, ''));
  v_last    text := btrim(coalesce(p_last_name, ''));
  v_email   text := lower(btrim(coalesce(p_email, '')));
  v_phone   text := regexp_replace(coalesce(p_phone, ''), '[^0-9]', '', 'g');
  v_note    text := btrim(coalesce(p_note, ''));
  v_iphash  text := private.client_ip_hash();
begin
  if p_reason is null or not (p_reason = any (private.visit_reasons())) then
    raise exception 'Please choose a reason for the visit.' using errcode = 'P0001';
  end if;
  if p_patient_type is null or p_patient_type not in ('new', 'existing') then
    raise exception 'Please say whether you have visited this dentist before.' using errcode = 'P0001';
  end if;
  if char_length(v_first) not between 1 and 60 or char_length(v_last) not between 1 and 60 then
    raise exception 'Please enter the patient''s first and last name.' using errcode = 'P0001';
  end if;
  if p_dob is null or p_dob < date '1900-01-01' or p_dob > current_date then
    raise exception 'Please enter a valid date of birth.' using errcode = 'P0001';
  end if;
  if char_length(v_phone) = 11 and left(v_phone, 1) = '1' then
    v_phone := substr(v_phone, 2);
  end if;
  if v_phone !~ '^[2-9][0-9]{2}[2-9][0-9]{6}$' then
    raise exception 'Please enter a 10-digit US phone number.' using errcode = 'P0001';
  end if;
  if v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' or char_length(v_email) > 254 then
    raise exception 'Please enter a valid email address.' using errcode = 'P0001';
  end if;
  if char_length(v_note) > 100 then
    raise exception 'The note can be up to 100 characters.' using errcode = 'P0001';
  end if;

  select o.minutes, o.timezone into v_minutes, v_tz
  from public.get_open_slots(p_npi) o where o.starts_at = p_starts_at;
  if v_minutes is null then
    raise exception 'That time is no longer available. Please pick another one.' using errcode = 'P0001', hint = 'slot_unavailable';
  end if;

  -- Limits that keep one person from filling a calendar.
  if exists (select 1 from public.appointments a
             where a.npi = p_npi and lower(a.email) = v_email and a.status = 'booked' and a.starts_at > now()
               and lower(a.first_name) = lower(v_first) and a.date_of_birth = p_dob) then
    raise exception 'This patient already has an upcoming appointment with this dentist.' using errcode = 'P0001';
  end if;
  if (select count(*) from public.appointments a
      where lower(a.email) = v_email and a.status = 'booked' and a.starts_at > now()) >= 5 then
    raise exception 'This email already has 5 upcoming appointments.' using errcode = 'P0001';
  end if;
  if v_iphash is not null and (select count(*) from public.appointments a
      where a.ip_hash = v_iphash and a.created_at > now() - interval '1 hour') >= 5 then
    raise exception 'Too many bookings from this connection. Please try again later.' using errcode = 'P0001';
  end if;

  insert into public.appointments (npi, starts_at, ends_at, reason, patient_type, booked_for,
                                   first_name, last_name, date_of_birth, phone, email, note, ip_hash)
  values (p_npi, p_starts_at, p_starts_at + make_interval(mins => v_minutes), p_reason, p_patient_type,
          case when p_booked_for = 'someone_else' then 'someone_else' else 'self' end,
          v_first, v_last, p_dob, v_phone, v_email, v_note, v_iphash)
  returning id, cancel_token into v_id, v_token;

  return json_build_object('id', v_id, 'token', v_token, 'starts_at', p_starts_at,
                           'minutes', v_minutes, 'timezone', v_tz);
exception
  when exclusion_violation then
    raise exception 'That time was just taken. Please pick another one.' using errcode = 'P0001', hint = 'slot_unavailable';
end $$;

-- An appointment, found by the secret token the patient was given.
create or replace function public.get_appointment(p_token uuid) returns json
language sql stable security definer set search_path = '' as $$
  select json_build_object(
    'npi', a.npi, 'status', a.status, 'starts_at', a.starts_at,
    'minutes', (extract(epoch from a.ends_at - a.starts_at) / 60)::int,
    'timezone', coalesce(pr.timezone, 'America/New_York'),
    'first_name', a.first_name, 'reason', a.reason, 'patient_type', a.patient_type,
    'cancelled_by', a.cancelled_by,
    'can_change', a.status = 'booked' and a.starts_at > now(),
    'dentist', d.name || case when d.credential <> '' then ', ' || d.credential else '' end,
    'phone', d.phone, 'address', d.address, 'city', d.city, 'url', d.url)
  from public.appointments a
  join public.dentists d on d.npi = a.npi
  left join public.practices pr on pr.npi = a.npi
  where a.cancel_token = p_token
$$;

create or replace function public.cancel_appointment(p_token uuid) returns json
language plpgsql volatile security definer set search_path = '' as $$
begin
  update public.appointments
     set status = 'cancelled', cancelled_by = 'patient', cancelled_at = now()
   where cancel_token = p_token and status = 'booked' and starts_at > now();
  if not found then
    raise exception 'This appointment can no longer be cancelled online. Please call the office.' using errcode = 'P0001';
  end if;
  return public.get_appointment(p_token);
end $$;

create or replace function public.reschedule_appointment(p_token uuid, p_new_start timestamptz) returns json
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_id      bigint;
  v_npi     text;
  v_minutes int;
begin
  select a.id, a.npi into v_id, v_npi
  from public.appointments a
  where a.cancel_token = p_token and a.status = 'booked' and a.starts_at > now();
  if v_id is null then
    raise exception 'This appointment can no longer be changed online. Please call the office.' using errcode = 'P0001';
  end if;
  select o.minutes into v_minutes from public.get_open_slots(v_npi, v_id) o where o.starts_at = p_new_start;
  if v_minutes is null then
    raise exception 'That time is no longer available. Please pick another one.' using errcode = 'P0001', hint = 'slot_unavailable';
  end if;
  update public.appointments
     set starts_at = p_new_start, ends_at = p_new_start + make_interval(mins => v_minutes), rescheduled_at = now()
   where id = v_id;
  return public.get_appointment(p_token);
exception
  when exclusion_violation then
    raise exception 'That time was just taken. Please pick another one.' using errcode = 'P0001', hint = 'slot_unavailable';
end $$;

-- ---------------------------------------------------------------- dentists (signed in)

-- Anyone can claim a listing. The claim waits for an admin; nothing changes until then.
create or replace function public.submit_claim(p_npi text, p_full_name text, p_email text,
                                               p_role text, p_phone text default '') returns json
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_npi    text := btrim(coalesce(p_npi, ''));
  v_name   text := btrim(coalesce(p_full_name, ''));
  v_email  text := lower(btrim(coalesce(p_email, '')));
  v_phone  text := btrim(coalesce(p_phone, ''));
  v_iphash text := private.client_ip_hash();
  v_id     bigint;
begin
  if v_npi !~ '^[0-9]{10}$' then
    raise exception 'The NPI number must be exactly 10 digits.' using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.dentists d where d.npi = v_npi) then
    raise exception 'We could not find that NPI number in our Florida listings.' using errcode = 'P0001';
  end if;
  if char_length(v_name) not between 2 and 120 then
    raise exception 'Please enter your name.' using errcode = 'P0001';
  end if;
  if v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' or char_length(v_email) > 254 then
    raise exception 'Please enter a valid work email.' using errcode = 'P0001';
  end if;
  if char_length(v_phone) > 30 then
    raise exception 'Please check the phone number.' using errcode = 'P0001';
  end if;
  if p_role is null or p_role not in ('Dentist', 'Office manager', 'Other') then
    raise exception 'Please choose your role.' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.claims c where c.npi = v_npi and c.status = 'approved' and lower(c.email) <> v_email) then
    raise exception 'This listing has already been claimed. If this is your practice, email support@dentistryusa.com.' using errcode = 'P0001';
  end if;
  if v_iphash is not null and (select count(*) from public.claims c
      where c.ip_hash = v_iphash and c.created_at > now() - interval '1 hour') >= 10 then
    raise exception 'Too many claims from this connection. Please try again later.' using errcode = 'P0001';
  end if;

  -- Sending the same claim twice keeps the first one.
  select c.id into v_id from public.claims c
  where c.npi = v_npi and lower(c.email) = v_email and c.status in ('pending', 'approved');
  if v_id is null then
    insert into public.claims (npi, full_name, email, phone, role, ip_hash)
    values (v_npi, v_name, v_email, v_phone, p_role, v_iphash)
    returning id into v_id;
  end if;
  return json_build_object('id', v_id, 'npi', v_npi,
                           'status', (select c.status from public.claims c where c.id = v_id));
end $$;

-- "Remove my listing" or "stop emailing me".
create or replace function public.submit_removal(p_npi text, p_request text, p_full_name text,
                                                 p_email text, p_note text default '') returns json
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_npi    text := nullif(btrim(coalesce(p_npi, '')), '');
  v_name   text := btrim(coalesce(p_full_name, ''));
  v_email  text := lower(btrim(coalesce(p_email, '')));
  v_note   text := btrim(coalesce(p_note, ''));
  v_iphash text := private.client_ip_hash();
  v_id     bigint;
begin
  if v_npi is not null and v_npi !~ '^[0-9]{10}$' then
    raise exception 'The NPI number must be exactly 10 digits.' using errcode = 'P0001';
  end if;
  if p_request is null or p_request not in ('remove_listing', 'stop_emails') then
    raise exception 'Please choose what you would like us to do.' using errcode = 'P0001';
  end if;
  if p_request = 'remove_listing' and v_npi is null then
    raise exception 'Please enter the NPI number of the listing to remove.' using errcode = 'P0001';
  end if;
  if char_length(v_name) not between 2 and 120 then
    raise exception 'Please enter your name.' using errcode = 'P0001';
  end if;
  if v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' or char_length(v_email) > 254 then
    raise exception 'Please enter a valid email address.' using errcode = 'P0001';
  end if;
  if char_length(v_note) > 500 then
    raise exception 'The note can be up to 500 characters.' using errcode = 'P0001';
  end if;
  if v_iphash is not null and (select count(*) from public.removal_requests r
      where r.ip_hash = v_iphash and r.created_at > now() - interval '1 hour') >= 10 then
    raise exception 'Too many requests from this connection. Please try again later.' using errcode = 'P0001';
  end if;

  insert into public.removal_requests (npi, request, full_name, email, note, ip_hash)
  values (v_npi, p_request, v_name, v_email, v_note, v_iphash)
  returning id into v_id;
  return json_build_object('id', v_id);
end $$;

-- Replaces a listing's weekly hours. p_hours: [{"weekday":1,"start":"09:00","end":"17:00"}, ...]
create or replace function public.save_weekly_hours(p_npi text, p_hours json) returns int
language plpgsql volatile security definer set search_path = '' as $$
begin
  if not public.owns_npi(p_npi) then
    raise exception 'You can only change hours for a listing you own.' using errcode = 'P0001';
  end if;
  if json_array_length(coalesce(p_hours, '[]'::json)) > 21 then
    raise exception 'Too many time ranges.' using errcode = 'P0001';
  end if;
  delete from public.weekly_hours where npi = p_npi;
  insert into public.weekly_hours (npi, weekday, start_time, end_time)
  select p_npi, (x ->> 'weekday')::int, (x ->> 'start')::time, (x ->> 'end')::time
  from json_array_elements(coalesce(p_hours, '[]'::json)) x;
  if exists (select 1 from public.weekly_hours a
             join public.weekly_hours b on a.npi = b.npi and a.weekday = b.weekday
                                       and a.start_time < b.start_time and b.start_time < a.end_time
             where a.npi = p_npi) then
    raise exception 'Two time ranges on the same day overlap.' using errcode = 'P0001';
  end if;
  return (select count(*) from public.weekly_hours where npi = p_npi);
exception
  when check_violation then
    raise exception 'Each closing time must be after the opening time.' using errcode = 'P0001';
  when unique_violation then
    raise exception 'Two time ranges on the same day start at the same time.' using errcode = 'P0001';
  when invalid_datetime_format or datetime_field_overflow or invalid_text_representation or not_null_violation then
    raise exception 'Please enter times like 09:00.' using errcode = 'P0001';
end $$;

create or replace function public.dentist_cancel(p_id bigint) returns boolean
language plpgsql volatile security definer set search_path = '' as $$
begin
  update public.appointments
     set status = 'cancelled', cancelled_by = 'practice', cancelled_at = now()
   where id = p_id and status = 'booked' and public.owns_npi(npi);
  return found;
end $$;

-- ---------------------------------------------------------------- admins

create or replace function public.admin_inbox() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_admin() then
    raise exception 'Admins only.' using errcode = 'P0001';
  end if;
  return json_build_object(
    'claims', (select coalesce(json_agg(row_to_json(t)), '[]'::json)
               from (select c.id, c.npi, c.full_name, c.email, c.phone, c.role, c.status, c.created_at, c.reviewed_at,
                            d.name as dentist, d.city, d.url
                     from public.claims c join public.dentists d on d.npi = c.npi
                     order by (c.status = 'pending') desc, c.created_at desc
                     limit 300) t),
    'removals', (select coalesce(json_agg(row_to_json(t)), '[]'::json)
                 from (select r.id, r.npi, r.request, r.full_name, r.email, r.note, r.status, r.created_at, r.handled_at,
                              d.name as dentist, d.city, d.url
                       from public.removal_requests r left join public.dentists d on d.npi = r.npi
                       order by (r.status = 'new') desc, r.created_at desc
                       limit 300) t));
end $$;

create or replace function public.close_removal(p_id bigint) returns boolean
language plpgsql volatile security definer set search_path = '' as $$
begin
  if not public.is_admin() then
    raise exception 'Admins only.' using errcode = 'P0001';
  end if;
  update public.removal_requests set status = 'done', handled_at = now() where id = p_id and status = 'new';
  return found;
end $$;

create or replace function public.review_claim(p_id bigint, p_approve boolean) returns json
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_npi text;
begin
  if not public.is_admin() then
    raise exception 'Admins only.' using errcode = 'P0001';
  end if;
  update public.claims
     set status = case when p_approve then 'approved' else 'rejected' end, reviewed_at = now()
   where id = p_id
  returning npi into v_npi;
  if v_npi is null then
    raise exception 'That claim no longer exists.' using errcode = 'P0001';
  end if;
  if p_approve then
    insert into public.practices (npi) values (v_npi) on conflict (npi) do nothing;
  end if;
  return json_build_object('id', p_id, 'npi', v_npi, 'status', case when p_approve then 'approved' else 'rejected' end);
exception
  when unique_violation then
    raise exception 'Another account already owns this listing. Reject that claim first.' using errcode = 'P0001';
end $$;

-- ---------------------------------------------------------------- who may call what

revoke all on function public.is_admin(), public.owns_npi(text), public.get_open_slots(text, bigint),
  public.booking_slots(text), public.online_listings(),
  public.book_appointment(text, timestamptz, text, text, text, text, date, text, text, text, text),
  public.get_appointment(uuid), public.cancel_appointment(uuid), public.reschedule_appointment(uuid, timestamptz),
  public.submit_claim(text, text, text, text, text), public.submit_removal(text, text, text, text, text),
  public.save_weekly_hours(text, json), public.dentist_cancel(bigint),
  public.admin_inbox(), public.review_claim(bigint, boolean), public.close_removal(bigint)
  from public, anon, authenticated;

grant execute on function public.booking_slots(text), public.online_listings(),
  public.book_appointment(text, timestamptz, text, text, text, text, date, text, text, text, text),
  public.get_appointment(uuid), public.cancel_appointment(uuid), public.reschedule_appointment(uuid, timestamptz),
  public.submit_claim(text, text, text, text, text), public.submit_removal(text, text, text, text, text)
  to anon, authenticated;

grant execute on function public.is_admin(), public.owns_npi(text),
  public.save_weekly_hours(text, json), public.dentist_cancel(bigint),
  public.admin_inbox(), public.review_claim(bigint, boolean), public.close_removal(bigint)
  to authenticated;
