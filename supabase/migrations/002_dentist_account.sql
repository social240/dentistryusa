-- DentistryUSA: the dentist's own account (/account/) and the booking screens.
-- Run after 001_booking.sql.
--
-- What changes:
--   * A dentist owns a listing only when the email on the approved claim is the
--     signed-in user's CONFIRMED email (auth.users.email_confirmed_at), not just
--     the email claim in the token.
--   * Signed-in users no longer read or write the claims, practices, hours or
--     appointments tables directly. Everything goes through the functions below,
--     which check ownership themselves.
--   * my_account(): what /account/ shows (listings, settings, hours, appointments).
--   * save_practice(): booking settings and weekly hours in one save.
--   * booking_slots() also says whether the listing has been claimed.

-- The signed-in user's email, lower case, only if they have confirmed it.
create or replace function private.verified_email() returns text
language sql stable set search_path = '' as $$
  select lower(u.email) from auth.users u
  where u.id = (select auth.uid()) and u.email_confirmed_at is not null
$$;
revoke all on function private.verified_email() from public;

create or replace function public.owns_npi(p_npi text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.claims c
                 where c.npi = p_npi and c.status = 'approved'
                   and lower(c.email) = private.verified_email())
$$;

-- ---------------------------------------------------------------- tables: functions only
revoke all on public.claims, public.practices, public.weekly_hours, public.appointments from anon, authenticated;
drop policy if exists "Own claims, or all for admins" on public.claims;
drop policy if exists "Owners and admins read settings" on public.practices;
drop policy if exists "Owners change settings" on public.practices;
drop policy if exists "Owners and admins read hours" on public.weekly_hours;
drop policy if exists "Owners read their appointments" on public.appointments;

-- ---------------------------------------------------------------- profile pages (anyone)
create or replace function public.booking_slots(p_npi text) returns json
language sql stable security definer set search_path = '' as $$
  select json_build_object(
    'claimed', exists (select 1 from public.claims c where c.npi = p_npi and c.status = 'approved'),
    'enabled', coalesce((select pr.booking_enabled
                                and exists (select 1 from public.claims c where c.npi = pr.npi and c.status = 'approved')
                         from public.practices pr where pr.npi = p_npi), false),
    'timezone', coalesce((select pr.timezone from public.practices pr where pr.npi = p_npi), 'America/New_York'),
    'minutes', (select pr.slot_minutes from public.practices pr where pr.npi = p_npi),
    'days_ahead', (select pr.days_ahead from public.practices pr where pr.npi = p_npi),
    'slots', coalesce((select json_agg(o.starts_at order by o.starts_at) from public.get_open_slots(p_npi) o), '[]'::json))
$$;

-- ---------------------------------------------------------------- the dentist's account (signed in)

-- Listings the signed-in dentist owns (with settings, hours and appointments from
-- yesterday on), and claims of theirs still waiting for review.
create or replace function public.my_account() returns json
language plpgsql stable security definer set search_path = '' as $$
declare
  v_email text := private.verified_email();
begin
  if v_email is null then
    raise exception 'Please sign in again.' using errcode = 'P0001';
  end if;
  return json_build_object(
    'email', v_email,
    'pending', (select coalesce(json_agg(json_build_object('npi', c.npi, 'dentist', d.name, 'city', d.city, 'url', d.url,
                                                           'created_at', c.created_at) order by c.created_at desc), '[]'::json)
                from public.claims c join public.dentists d on d.npi = c.npi
                where lower(c.email) = v_email and c.status = 'pending'),
    'listings', (select coalesce(json_agg(json_build_object(
                   'npi', d.npi, 'dentist', d.name, 'credential', d.credential, 'specialty', d.specialty,
                   'city', d.city, 'url', d.url,
                   'booking_enabled', coalesce(pr.booking_enabled, false),
                   'slot_minutes', coalesce(pr.slot_minutes, 30),
                   'min_notice_hours', coalesce(pr.min_notice_hours, 2),
                   'days_ahead', coalesce(pr.days_ahead, 28),
                   'timezone', coalesce(pr.timezone, 'America/New_York'),
                   'hours', (select coalesce(json_agg(json_build_object('weekday', h.weekday,
                                                                         'start', to_char(h.start_time, 'HH24:MI'),
                                                                         'end', to_char(h.end_time, 'HH24:MI'))
                                                      order by h.weekday, h.start_time), '[]'::json)
                             from public.weekly_hours h where h.npi = d.npi),
                   'appointments', (select coalesce(json_agg(row_to_json(a) order by a.starts_at), '[]'::json)
                                    from (select ap.id, ap.starts_at,
                                                 (extract(epoch from ap.ends_at - ap.starts_at) / 60)::int as minutes,
                                                 ap.status, ap.cancelled_by, ap.reason, ap.patient_type, ap.booked_for,
                                                 ap.first_name, ap.last_name, ap.date_of_birth, ap.phone, ap.email, ap.note,
                                                 ap.created_at, ap.rescheduled_at
                                          from public.appointments ap
                                          where ap.npi = d.npi and ap.starts_at > now() - interval '1 day'
                                          order by ap.starts_at
                                          limit 300) a))
                 order by d.name), '[]'::json)
                 from public.claims c
                 join public.dentists d on d.npi = c.npi
                 left join public.practices pr on pr.npi = c.npi
                 where lower(c.email) = v_email and c.status = 'approved'));
end $$;

-- Booking settings and weekly hours, saved together.
-- p_hours: [{"weekday":1,"start":"09:00","end":"17:00"}, ...]  (0 = Sunday)
create or replace function public.save_practice(p_npi text, p_enabled boolean, p_slot_minutes int, p_min_notice_hours int,
                                                p_days_ahead int, p_timezone text, p_hours json) returns json
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_hours int;
begin
  if not public.owns_npi(p_npi) then
    raise exception 'You can only change a listing you own.' using errcode = 'P0001';
  end if;
  if p_slot_minutes is null or p_slot_minutes not in (15, 20, 30, 45, 60) then
    raise exception 'Choose an appointment length of 15, 20, 30, 45 or 60 minutes.' using errcode = 'P0001';
  end if;
  if p_min_notice_hours is null or p_min_notice_hours not between 0 and 72 then
    raise exception 'The notice you need must be between 0 and 72 hours.' using errcode = 'P0001';
  end if;
  if p_days_ahead is null or p_days_ahead not between 1 and 60 then
    raise exception 'Patients can book between 1 and 60 days ahead.' using errcode = 'P0001';
  end if;
  if p_timezone is null or p_timezone not in ('America/New_York', 'America/Chicago') then
    raise exception 'Choose Eastern or Central time.' using errcode = 'P0001';
  end if;

  -- The practice row first: weekly_hours points at it.
  insert into public.practices (npi, booking_enabled, slot_minutes, min_notice_hours, days_ahead, timezone)
  values (p_npi, coalesce(p_enabled, false), p_slot_minutes, p_min_notice_hours, p_days_ahead, p_timezone)
  on conflict (npi) do update
    set booking_enabled = excluded.booking_enabled, slot_minutes = excluded.slot_minutes,
        min_notice_hours = excluded.min_notice_hours, days_ahead = excluded.days_ahead, timezone = excluded.timezone;

  v_hours := public.save_weekly_hours(p_npi, p_hours);
  if coalesce(p_enabled, false) and v_hours = 0 then
    raise exception 'Add your opening hours before you turn on online booking.' using errcode = 'P0001';
  end if;
  return json_build_object('npi', p_npi, 'booking_enabled', coalesce(p_enabled, false), 'hours', v_hours);
end $$;

-- ---------------------------------------------------------------- who may call what
revoke all on function public.my_account(), public.save_practice(text, boolean, int, int, int, text, json)
  from public, anon, authenticated;
grant execute on function public.my_account(), public.save_practice(text, boolean, int, int, int, text, json)
  to authenticated;
-- booking_slots keeps its grants (create or replace does not change them).
