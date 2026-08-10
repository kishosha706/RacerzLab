# P20 transient response and steering workload

Status: **Slice D backend verified**

The transient producer emits amplitude-relative onset, delay, rise, peak-response,
overshoot, settling, and steering/yaw path descriptors for one exact eligible-lap
phase window. These are calculated timing/response descriptors. They are not a
vehicle time constant, understeer coefficient, stability derivative, transfer
function, or setup cause.

The workload producer consumes the preserved six-sample
`SteeringWheelTorque_ST` stream at its effective 360 Hz timing. It reports torque
distribution, reversal, high-frequency variation, steering perturbation,
torque/angle path, correction density, and `steering_effort_work_proxy` values.
The work-like value is a relative driver-control proxy, not steering energy, rack
work, tire aligning torque, tire force, fatigue, impairment, or exhaustion.

Comparisons require all of the following:

- identical complete FFB fingerprint, including MaxForce and steering conversion;
- matched physical-position and speed context;
- matched driver context;
- healthy sub-tick clock;
- exact artifact-to-fingerprint binding.

The Atlanta Next Gen fixture preserved 360 Hz torque in every tested eligible-lap
phase window. Multiple detector-owned `full_throttle_exit` windows produced ready
transient descriptors and 120-780 sub-tick workload samples. Workload artifacts
remain `limited` because the fixture does not declare `SteeringWheelFFBEnabled`;
comparison is therefore blocked even though the single-run descriptive metrics
remain available.
