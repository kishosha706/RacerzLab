# Vehicle engineering profiles

Profiles in this directory are immutable, versioned, and source-backed. Missing
geometry and conventions remain `null`; generic vehicle knowledge is never used
to fill a car-specific constant.

The initial Next Gen Camaro profile is deliberately identity-only. Its source IBT
proves the exact car version and iRacing build but does not prove wheelbase, track
width, sensor locations, motion ratios, sign conventions, or damper bands. Metrics
requiring those fields must remain unavailable until an authoritative source is
recorded in a new profile version.
