-- Visits by country and (synthetic) device type
SELECT
    visits.country_code,                                               -- country code
    countries.country_name,                                            -- readable country name
    visits.device_type_synthetic,                                      -- synthetic device (label it in charts)
    COUNT(*) AS visits                                                 -- visits in this group
FROM visits                                                            -- Gold visits table
JOIN countries                                                         -- Gold countries table
    ON countries.country_code = visits.country_code                    -- match on the real code
GROUP BY visits.country_code, countries.country_name, visits.device_type_synthetic  -- one row per country and device
ORDER BY visits DESC, visits.country_code, visits.device_type_synthetic  -- biggest groups first
