-- 007: hypoglycaemia becomes its own safety trigger.
--
-- It was tempting to fold low blood sugar into medical_emergency, but the
-- correct first action differs: for mild-to-moderate hypoglycaemia the answer
-- is *eat something sweet now*, not *call an ambulance*. Sending someone to
-- 112 while they need 15g of glucose is worse advice than saying nothing, and
-- many users on medication reminders are diabetic — this is a likely event,
-- not an edge case.
--
-- Severe hypoglycaemia (unconscious, unable to swallow) is already caught by
-- the medical_emergency patterns, which run first.

begin;

alter table safety_events drop constraint if exists safety_events_trigger_check;
alter table safety_events add constraint safety_events_trigger_check
    check (trigger in ('medical_emergency', 'self_harm', 'medical_advice',
                       'scam', 'hypoglycemia'));

commit;
