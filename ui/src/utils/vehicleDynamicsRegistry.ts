export const p35RuntimeTrustManifest = {
  "schema_version": "p35.vehicle-dynamics-runtime-trust.v1",
  "runtime_trust_sha256": "5bc9139f42049f391015040948147f9de37af1b2da770ea99e10d1db72f74164",
  "graph_id": "p35vdg_c14af7ad22a752df5710a6e6",
  "graph_version": "2026.08.next-gen-oval.v1:c14af7ad22a7",
  "knowledge_version": "2026.08.p35-next-gen-oval.v1",
  "knowledge_graph_sha256": "c14af7ad22a752df5710a6e695b50f085fa4d15ecb20b271b3dc6205e3113030",
  "mechanisms": [
    {
      "mechanism_id": "mechanism:brake_entry_instability",
      "p20_mechanism_ids": [
        "braking_response",
        "corner_rotation"
      ],
      "p32_performance_mechanism_ids": [
        "braking_realization",
        "entry_rotation"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "brake",
        "entry"
      ],
      "response_regime": "transient",
      "component_family_ids": [
        "brakes",
        "tires",
        "weight_distribution"
      ],
      "inspection_tool_id": "inspect_brake_vehicle_response",
      "support_observation_contract_ids": [
        "observation:brake_entry_instability:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:brake_entry_instability:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:brake_entry_instability:support_discriminator",
        "observation:brake_entry_instability:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:brake_input",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "brake_01",
              "accepted_source_channel_ids": [
                "brake_01",
                "Brake"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:front_brake_pressure",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lf_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "lf_brake_line_pressure_bar",
                "LFbrakeLinePress"
              ]
            },
            {
              "channel_id": "rf_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "rf_brake_line_pressure_bar",
                "RFbrakeLinePress"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:rear_brake_pressure",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "lr_brake_line_pressure_bar",
                "LRbrakeLinePress"
              ]
            },
            {
              "channel_id": "rr_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "rr_brake_line_pressure_bar",
                "RRbrakeLinePress"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:front_wheel_response",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lf_speed",
              "accepted_source_channel_ids": [
                "lf_speed",
                "LFspeed"
              ]
            },
            {
              "channel_id": "rf_speed",
              "accepted_source_channel_ids": [
                "rf_speed",
                "RFspeed"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:rear_wheel_response",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_speed",
              "accepted_source_channel_ids": [
                "lr_speed",
                "LRspeed"
              ]
            },
            {
              "channel_id": "rr_speed",
              "accepted_source_channel_ids": [
                "rr_speed",
                "RRspeed"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:yaw_response",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:steering_input",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.brake_vehicle_response:"
    },
    {
      "mechanism_id": "mechanism:brake_release_rotation_deficit",
      "p20_mechanism_ids": [
        "braking_response",
        "corner_rotation",
        "damper_response"
      ],
      "p32_performance_mechanism_ids": [
        "brake_release_transition",
        "entry_rotation"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "entry"
      ],
      "response_regime": "transient",
      "component_family_ids": [
        "brakes",
        "dampers",
        "tires"
      ],
      "inspection_tool_id": "inspect_transient_settling",
      "support_observation_contract_ids": [
        "observation:brake_release_rotation_deficit:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:brake_release_rotation_deficit:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:brake_release_rotation_deficit:support_discriminator",
        "observation:brake_release_rotation_deficit:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:brake_input",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "brake_01",
              "accepted_source_channel_ids": [
                "brake_01",
                "Brake"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:front_brake_pressure",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lf_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "lf_brake_line_pressure_bar",
                "LFbrakeLinePress"
              ]
            },
            {
              "channel_id": "rf_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "rf_brake_line_pressure_bar",
                "RFbrakeLinePress"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:rear_brake_pressure",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "lr_brake_line_pressure_bar",
                "LRbrakeLinePress"
              ]
            },
            {
              "channel_id": "rr_brake_line_pressure_bar",
              "accepted_source_channel_ids": [
                "rr_brake_line_pressure_bar",
                "RRbrakeLinePress"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:yaw_response",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:steering_input",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:shock_velocity",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "shock_velocity",
              "accepted_source_channel_ids": [
                "shock_velocity",
                "lf_shock_vel_in_s",
                "rf_shock_vel_in_s",
                "lr_shock_vel_in_s",
                "rr_shock_vel_in_s",
                "LFSHshockVel",
                "LFshockVel",
                "LRSHshockVel",
                "LRshockVel",
                "RFSHshockVel",
                "RFshockVel",
                "RRSHshockVel",
                "RRshockVel"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.transient_settling:"
    },
    {
      "mechanism_id": "mechanism:center_rotation_deficit",
      "p20_mechanism_ids": [
        "corner_rotation",
        "tire_state",
        "platform_response"
      ],
      "p32_performance_mechanism_ids": [
        "center_rotation",
        "speed_retention"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "center"
      ],
      "response_regime": "steady_state",
      "component_family_ids": [
        "tires",
        "alignment",
        "springs",
        "anti_roll_bars",
        "platform",
        "weight_distribution",
        "differential",
        "steering"
      ],
      "inspection_tool_id": "inspect_steady_state_balance",
      "support_observation_contract_ids": [
        "observation:center_rotation_deficit:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:center_rotation_deficit:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:center_rotation_deficit:support_discriminator",
        "observation:center_rotation_deficit:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:steering_deg",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:speed_mph",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "speed_mph",
              "accepted_source_channel_ids": [
                "speed_mph",
                "speed_mps",
                "Speed"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:lat_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lat_accel",
              "accepted_source_channel_ids": [
                "lat_accel",
                "LatAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.steady_state_balance:"
    },
    {
      "mechanism_id": "mechanism:disturbance_compliance_issue",
      "p20_mechanism_ids": [
        "damper_response",
        "platform_response"
      ],
      "p32_performance_mechanism_ids": [
        "disturbance_compliance",
        "stability_workload"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "transition",
        "turn_in",
        "entry",
        "exit"
      ],
      "response_regime": "transient",
      "component_family_ids": [
        "dampers",
        "springs",
        "platform",
        "tires"
      ],
      "inspection_tool_id": "inspect_transient_settling",
      "support_observation_contract_ids": [
        "observation:disturbance_compliance_issue:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:disturbance_compliance_issue:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:disturbance_compliance_issue:support_discriminator",
        "observation:disturbance_compliance_issue:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:vert_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "vert_accel",
              "accepted_source_channel_ids": [
                "vert_accel",
                "VertAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:shock_velocity",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "shock_velocity",
              "accepted_source_channel_ids": [
                "shock_velocity",
                "lf_shock_vel_in_s",
                "rf_shock_vel_in_s",
                "lr_shock_vel_in_s",
                "rr_shock_vel_in_s",
                "LFSHshockVel",
                "LFshockVel",
                "LRSHshockVel",
                "LRshockVel",
                "RFSHshockVel",
                "RFshockVel",
                "RRSHshockVel",
                "RRshockVel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:shock_deflection",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "shock_deflection",
              "accepted_source_channel_ids": [
                "shock_deflection",
                "lf_shock_defl_in",
                "rf_shock_defl_in",
                "lr_shock_defl_in",
                "rr_shock_defl_in",
                "LFSHshockDefl",
                "LFshockDefl",
                "LRSHshockDefl",
                "LRshockDefl",
                "RFSHshockDefl",
                "RFshockDefl",
                "RRSHshockDefl",
                "RRshockDefl"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.transient_settling:"
    },
    {
      "mechanism_id": "mechanism:front_roll_support_limitation",
      "p20_mechanism_ids": [
        "corner_rotation",
        "platform_response"
      ],
      "p32_performance_mechanism_ids": [
        "center_rotation",
        "platform_consistency"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "turn_in",
        "entry",
        "center"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "springs",
        "anti_roll_bars",
        "tires"
      ],
      "inspection_tool_id": "inspect_roll_response",
      "support_observation_contract_ids": [
        "observation:front_roll_support_limitation:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:front_roll_support_limitation:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:front_roll_support_limitation:support_discriminator",
        "observation:front_roll_support_limitation:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:steering_deg",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:front_shock_deflection_pair",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lf_shock_deflection",
              "accepted_source_channel_ids": [
                "lf_shock_deflection",
                "lf_shock_defl_in",
                "LFSHshockDefl",
                "LFshockDefl"
              ]
            },
            {
              "channel_id": "rf_shock_deflection",
              "accepted_source_channel_ids": [
                "rf_shock_deflection",
                "rf_shock_defl_in",
                "RFSHshockDefl",
                "RFshockDefl"
              ]
            }
          ],
          "minimum_alternatives": 2
        }
      ],
      "focus_artifact_prefix": "p35.focus.roll_response:"
    },
    {
      "mechanism_id": "mechanism:front_tire_saturation_like",
      "p20_mechanism_ids": [
        "tire_state",
        "corner_rotation"
      ],
      "p32_performance_mechanism_ids": [
        "turn_in_response",
        "center_rotation"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "turn_in",
        "entry",
        "center"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "tires",
        "alignment",
        "steering"
      ],
      "inspection_tool_id": "inspect_tire_demand",
      "support_observation_contract_ids": [
        "observation:front_tire_saturation_like:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:front_tire_saturation_like:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:front_tire_saturation_like:support_discriminator",
        "observation:front_tire_saturation_like:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:steering_deg",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:lat_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lat_accel",
              "accepted_source_channel_ids": [
                "lat_accel",
                "LatAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:speed_mph",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "speed_mph",
              "accepted_source_channel_ids": [
                "speed_mph",
                "speed_mps",
                "Speed"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.tire_demand:"
    },
    {
      "mechanism_id": "mechanism:gearing_headroom_limitation",
      "p20_mechanism_ids": [
        "powertrain_response"
      ],
      "p32_performance_mechanism_ids": [
        "gearing_headroom",
        "straight_acceleration"
      ],
      "allowed_time_origin_kinds": [
        "local_generation"
      ],
      "relevant_phases": [
        "straight",
        "following_straight"
      ],
      "response_regime": "steady_state",
      "component_family_ids": [
        "final_drive"
      ],
      "inspection_tool_id": "inspect_gear_acceleration_response",
      "support_observation_contract_ids": [
        "observation:gearing_headroom_limitation:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:gearing_headroom_limitation:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:gearing_headroom_limitation:support_discriminator",
        "observation:gearing_headroom_limitation:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:rpm",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "rpm",
              "accepted_source_channel_ids": [
                "rpm",
                "RPM"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:gear",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "gear",
              "accepted_source_channel_ids": [
                "gear",
                "Gear"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:speed_mph",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "speed_mph",
              "accepted_source_channel_ids": [
                "speed_mph",
                "speed_mps",
                "Speed"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:throttle_pct",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "throttle_pct",
              "accepted_source_channel_ids": [
                "throttle_pct",
                "throttle_01",
                "Throttle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:long_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "long_accel",
              "accepted_source_channel_ids": [
                "long_accel",
                "LongAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.gear_acceleration_response:"
    },
    {
      "mechanism_id": "mechanism:platform_pitch_migration",
      "p20_mechanism_ids": [
        "platform_response",
        "braking_response"
      ],
      "p32_performance_mechanism_ids": [
        "braking_realization",
        "platform_consistency"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "brake",
        "entry",
        "throttle_pickup"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "platform",
        "springs"
      ],
      "inspection_tool_id": "inspect_pitch_response",
      "support_observation_contract_ids": [
        "observation:platform_pitch_migration:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:platform_pitch_migration:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:platform_pitch_migration:support_discriminator",
        "observation:platform_pitch_migration:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:front_ride_height",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lf_ride_height",
              "accepted_source_channel_ids": [
                "lf_ride_height",
                "lf_ride_height_m",
                "LFrideHeight"
              ]
            },
            {
              "channel_id": "rf_ride_height",
              "accepted_source_channel_ids": [
                "rf_ride_height",
                "rf_ride_height_m",
                "RFrideHeight"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:rear_ride_height",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lr_ride_height",
              "accepted_source_channel_ids": [
                "lr_ride_height",
                "lr_ride_height_m",
                "LRrideHeight"
              ]
            },
            {
              "channel_id": "rr_ride_height",
              "accepted_source_channel_ids": [
                "rr_ride_height",
                "rr_ride_height_m",
                "RRrideHeight"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:front_shock_deflection",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lf_shock_deflection",
              "accepted_source_channel_ids": [
                "lf_shock_deflection",
                "lf_shock_defl_in",
                "LFSHshockDefl",
                "LFshockDefl"
              ]
            },
            {
              "channel_id": "rf_shock_deflection",
              "accepted_source_channel_ids": [
                "rf_shock_deflection",
                "rf_shock_defl_in",
                "RFSHshockDefl",
                "RFshockDefl"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:rear_shock_deflection",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lr_shock_deflection",
              "accepted_source_channel_ids": [
                "lr_shock_deflection",
                "lr_shock_defl_in",
                "LRSHshockDefl",
                "LRshockDefl"
              ]
            },
            {
              "channel_id": "rr_shock_deflection",
              "accepted_source_channel_ids": [
                "rr_shock_deflection",
                "rr_shock_defl_in",
                "RRSHshockDefl",
                "RRshockDefl"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:brake_pct",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "brake_pct",
              "accepted_source_channel_ids": [
                "brake_pct",
                "brake_01",
                "Brake"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:speed_mph",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "speed_mph",
              "accepted_source_channel_ids": [
                "speed_mph",
                "speed_mps",
                "Speed"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.pitch_response:"
    },
    {
      "mechanism_id": "mechanism:platform_roll_migration",
      "p20_mechanism_ids": [
        "platform_response",
        "corner_rotation"
      ],
      "p32_performance_mechanism_ids": [
        "center_rotation",
        "platform_consistency"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "turn_in",
        "entry",
        "center",
        "exit"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "platform",
        "springs",
        "anti_roll_bars"
      ],
      "inspection_tool_id": "inspect_traffic_platform_response",
      "support_observation_contract_ids": [
        "observation:platform_roll_migration:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:platform_roll_migration:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:platform_roll_migration:support_discriminator",
        "observation:platform_roll_migration:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:left_ride_height",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lf_ride_height",
              "accepted_source_channel_ids": [
                "lf_ride_height",
                "lf_ride_height_m",
                "LFrideHeight"
              ]
            },
            {
              "channel_id": "lr_ride_height",
              "accepted_source_channel_ids": [
                "lr_ride_height",
                "lr_ride_height_m",
                "LRrideHeight"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:right_ride_height",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "rf_ride_height",
              "accepted_source_channel_ids": [
                "rf_ride_height",
                "rf_ride_height_m",
                "RFrideHeight"
              ]
            },
            {
              "channel_id": "rr_ride_height",
              "accepted_source_channel_ids": [
                "rr_ride_height",
                "rr_ride_height_m",
                "RRrideHeight"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:left_shock_deflection",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lf_shock_deflection",
              "accepted_source_channel_ids": [
                "lf_shock_deflection",
                "lf_shock_defl_in",
                "LFSHshockDefl",
                "LFshockDefl"
              ]
            },
            {
              "channel_id": "lr_shock_deflection",
              "accepted_source_channel_ids": [
                "lr_shock_deflection",
                "lr_shock_defl_in",
                "LRSHshockDefl",
                "LRshockDefl"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:right_shock_deflection",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "rf_shock_deflection",
              "accepted_source_channel_ids": [
                "rf_shock_deflection",
                "rf_shock_defl_in",
                "RFSHshockDefl",
                "RFshockDefl"
              ]
            },
            {
              "channel_id": "rr_shock_deflection",
              "accepted_source_channel_ids": [
                "rr_shock_deflection",
                "rr_shock_defl_in",
                "RRSHshockDefl",
                "RRshockDefl"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:steering_deg",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:speed_mph",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "speed_mph",
              "accepted_source_channel_ids": [
                "speed_mph",
                "speed_mps",
                "Speed"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.traffic_platform_response:"
    },
    {
      "mechanism_id": "mechanism:power_on_rotation_deficit",
      "p20_mechanism_ids": [
        "powertrain_response",
        "corner_rotation"
      ],
      "p32_performance_mechanism_ids": [
        "throttle_realization",
        "exit_traction"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "throttle_pickup",
        "exit"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "tires",
        "differential",
        "springs",
        "anti_roll_bars"
      ],
      "inspection_tool_id": "inspect_differential_response",
      "support_observation_contract_ids": [
        "observation:power_on_rotation_deficit:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:power_on_rotation_deficit:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:power_on_rotation_deficit:support_discriminator",
        "observation:power_on_rotation_deficit:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:throttle_pct",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "throttle_pct",
              "accepted_source_channel_ids": [
                "throttle_pct",
                "throttle_01",
                "Throttle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:long_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "long_accel",
              "accepted_source_channel_ids": [
                "long_accel",
                "LongAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:rear_wheel_speed_relationship",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_wheel_speed",
              "accepted_source_channel_ids": [
                "lr_wheel_speed",
                "lr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "LRspeed"
              ]
            },
            {
              "channel_id": "rr_wheel_speed",
              "accepted_source_channel_ids": [
                "rr_wheel_speed",
                "rr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "RRspeed"
              ]
            }
          ],
          "minimum_alternatives": 2
        }
      ],
      "focus_artifact_prefix": "p35.focus.differential_response:"
    },
    {
      "mechanism_id": "mechanism:power_on_rotation_excess",
      "p20_mechanism_ids": [
        "powertrain_response",
        "corner_rotation"
      ],
      "p32_performance_mechanism_ids": [
        "throttle_realization",
        "exit_traction"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "throttle_pickup",
        "exit"
      ],
      "response_regime": "transient",
      "component_family_ids": [
        "tires",
        "differential",
        "springs",
        "anti_roll_bars"
      ],
      "inspection_tool_id": "inspect_power_on_response",
      "support_observation_contract_ids": [
        "observation:power_on_rotation_excess:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:power_on_rotation_excess:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:power_on_rotation_excess:support_discriminator",
        "observation:power_on_rotation_excess:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:throttle_pct",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "throttle_pct",
              "accepted_source_channel_ids": [
                "throttle_pct",
                "throttle_01",
                "Throttle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:long_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "long_accel",
              "accepted_source_channel_ids": [
                "long_accel",
                "LongAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:rear_wheel_speed_relationship",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_wheel_speed",
              "accepted_source_channel_ids": [
                "lr_wheel_speed",
                "lr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "LRspeed"
              ]
            },
            {
              "channel_id": "rr_wheel_speed",
              "accepted_source_channel_ids": [
                "rr_wheel_speed",
                "rr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "RRspeed"
              ]
            }
          ],
          "minimum_alternatives": 2
        }
      ],
      "focus_artifact_prefix": "p35.focus.power_on_response:"
    },
    {
      "mechanism_id": "mechanism:rear_roll_support_limitation",
      "p20_mechanism_ids": [
        "corner_rotation",
        "platform_response"
      ],
      "p32_performance_mechanism_ids": [
        "center_rotation",
        "exit_traction"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "entry",
        "center",
        "throttle_pickup",
        "exit"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "springs",
        "anti_roll_bars",
        "tires"
      ],
      "inspection_tool_id": "inspect_platform_state",
      "support_observation_contract_ids": [
        "observation:rear_roll_support_limitation:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:rear_roll_support_limitation:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:rear_roll_support_limitation:support_discriminator",
        "observation:rear_roll_support_limitation:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:rear_shock_deflection_pair",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "lr_shock_deflection",
              "accepted_source_channel_ids": [
                "lr_shock_deflection",
                "lr_shock_defl_in",
                "LRSHshockDefl",
                "LRshockDefl"
              ]
            },
            {
              "channel_id": "rr_shock_deflection",
              "accepted_source_channel_ids": [
                "rr_shock_deflection",
                "rr_shock_defl_in",
                "RRSHshockDefl",
                "RRshockDefl"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:throttle_pct",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "throttle_pct",
              "accepted_source_channel_ids": [
                "throttle_pct",
                "throttle_01",
                "Throttle"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.platform_state:"
    },
    {
      "mechanism_id": "mechanism:rear_tire_saturation_like",
      "p20_mechanism_ids": [
        "tire_state",
        "powertrain_response"
      ],
      "p32_performance_mechanism_ids": [
        "exit_traction",
        "throttle_realization"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "entry",
        "center",
        "throttle_pickup",
        "exit"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "tires",
        "differential"
      ],
      "inspection_tool_id": "inspect_load_transfer",
      "support_observation_contract_ids": [
        "observation:rear_tire_saturation_like:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:rear_tire_saturation_like:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:rear_tire_saturation_like:support_discriminator",
        "observation:rear_tire_saturation_like:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:throttle_pct",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "throttle_pct",
              "accepted_source_channel_ids": [
                "throttle_pct",
                "throttle_01",
                "Throttle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:long_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "long_accel",
              "accepted_source_channel_ids": [
                "long_accel",
                "LongAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:lr_wheel_speed",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_wheel_speed",
              "accepted_source_channel_ids": [
                "lr_wheel_speed",
                "lr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "LRspeed"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:rr_wheel_speed",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "rr_wheel_speed",
              "accepted_source_channel_ids": [
                "rr_wheel_speed",
                "rr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "RRspeed"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.load_transfer:"
    },
    {
      "mechanism_id": "mechanism:scrub_like_resistance",
      "p20_mechanism_ids": [
        "resistance_scrub_like",
        "powertrain_response"
      ],
      "p32_performance_mechanism_ids": [
        "straight_acceleration",
        "path_efficiency"
      ],
      "allowed_time_origin_kinds": [
        "local_generation"
      ],
      "relevant_phases": [
        "straight",
        "following_straight"
      ],
      "response_regime": "steady_state",
      "component_family_ids": [
        "alignment",
        "tires"
      ],
      "inspection_tool_id": "inspect_alignment_response",
      "support_observation_contract_ids": [
        "observation:scrub_like_resistance:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:scrub_like_resistance:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:scrub_like_resistance:support_discriminator",
        "observation:scrub_like_resistance:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:steering_deg",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:speed_mph",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "speed_mph",
              "accepted_source_channel_ids": [
                "speed_mph",
                "speed_mps",
                "Speed"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:long_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "long_accel",
              "accepted_source_channel_ids": [
                "long_accel",
                "LongAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:front_wheel_speed_relationship",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lf_wheel_speed",
              "accepted_source_channel_ids": [
                "lf_wheel_speed",
                "lf_speed",
                "front_wheel_speed_mismatch",
                "front_wheel_speed_mismatch_raw",
                "front_wheel_speed_mismatch_corrected",
                "LFspeed"
              ]
            },
            {
              "channel_id": "rf_wheel_speed",
              "accepted_source_channel_ids": [
                "rf_wheel_speed",
                "rf_speed",
                "front_wheel_speed_mismatch",
                "front_wheel_speed_mismatch_raw",
                "front_wheel_speed_mismatch_corrected",
                "RFspeed"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:rear_wheel_speed_relationship",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_wheel_speed",
              "accepted_source_channel_ids": [
                "lr_wheel_speed",
                "lr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "LRspeed"
              ]
            },
            {
              "channel_id": "rr_wheel_speed",
              "accepted_source_channel_ids": [
                "rr_wheel_speed",
                "rr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "RRspeed"
              ]
            }
          ],
          "minimum_alternatives": 2
        }
      ],
      "focus_artifact_prefix": "p35.focus.alignment_response:"
    },
    {
      "mechanism_id": "mechanism:tire_state_migration",
      "p20_mechanism_ids": [
        "tire_state",
        "stint_trend"
      ],
      "p32_performance_mechanism_ids": [
        "tire_state_migration",
        "stability_workload"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "entry",
        "center",
        "exit",
        "following_straight"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "tires",
        "alignment"
      ],
      "inspection_tool_id": "inspect_tire_state_migration",
      "support_observation_contract_ids": [
        "observation:tire_state_migration:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:tire_state_migration:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:tire_state_migration:support_discriminator",
        "observation:tire_state_migration:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:lap",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lap",
              "accepted_source_channel_ids": [
                "lap",
                "Lap"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:steering_deg",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "steering_deg",
              "accepted_source_channel_ids": [
                "steering_deg",
                "steering_rad",
                "SteeringWheelAngle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:tire_temperature",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "tire_temperature",
              "accepted_source_channel_ids": [
                "tire_temperature",
                "lf_temp_left",
                "lf_temp_middle",
                "lf_temp_right",
                "rf_temp_left",
                "rf_temp_middle",
                "rf_temp_right",
                "lr_temp_left",
                "lr_temp_middle",
                "lr_temp_right",
                "rr_temp_left",
                "rr_temp_middle",
                "rr_temp_right",
                "LFtempL",
                "LFtempM",
                "LFtempR",
                "LRtempL",
                "LRtempM",
                "LRtempR",
                "RFtempL",
                "RFtempM",
                "RFtempR",
                "RRtempL",
                "RRtempM",
                "RRtempR"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:tire_pressure",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "tire_pressure",
              "accepted_source_channel_ids": [
                "tire_pressure",
                "lf_pressure",
                "rf_pressure",
                "lr_pressure",
                "rr_pressure",
                "LFpressure",
                "LRpressure",
                "RFpressure",
                "RRpressure"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:tire_wear",
          "evidence_layer_ids": [
            "vehicle_response",
            "tire_platform_state"
          ],
          "alternatives": [
            {
              "channel_id": "tire_wear",
              "accepted_source_channel_ids": [
                "tire_wear",
                "lf_wear_left",
                "lf_wear_middle",
                "lf_wear_right",
                "rf_wear_left",
                "rf_wear_middle",
                "rf_wear_right",
                "lr_wear_left",
                "lr_wear_middle",
                "lr_wear_right",
                "rr_wear_left",
                "rr_wear_middle",
                "rr_wear_right",
                "LFwearL",
                "LFwearM",
                "LFwearR",
                "LRwearL",
                "LRwearM",
                "LRwearR",
                "RFwearL",
                "RFwearM",
                "RFwearR",
                "RRwearL",
                "RRwearM",
                "RRwearR"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.tire_state_migration:"
    },
    {
      "mechanism_id": "mechanism:traction_limitation_like",
      "p20_mechanism_ids": [
        "powertrain_response",
        "tire_state"
      ],
      "p32_performance_mechanism_ids": [
        "exit_traction",
        "straight_acceleration"
      ],
      "allowed_time_origin_kinds": [
        "local_generation",
        "amplified",
        "surrendered"
      ],
      "relevant_phases": [
        "throttle_pickup",
        "exit",
        "following_straight"
      ],
      "response_regime": "both",
      "component_family_ids": [
        "tires",
        "differential"
      ],
      "inspection_tool_id": "inspect_tire_demand",
      "support_observation_contract_ids": [
        "observation:traction_limitation_like:support_discriminator"
      ],
      "contradiction_observation_contract_ids": [
        "observation:traction_limitation_like:contradiction"
      ],
      "discriminator_observation_contract_ids": [
        "observation:traction_limitation_like:support_discriminator",
        "observation:traction_limitation_like:contradiction"
      ],
      "support_required_evidence_layers": [
        "driver_input",
        "vehicle_demand",
        "vehicle_response",
        "tire_platform_state",
        "time_consequence"
      ],
      "support_required_channel_groups": [
        {
          "requirement_id": "support_channel:throttle_pct",
          "evidence_layer_ids": [
            "driver_input"
          ],
          "alternatives": [
            {
              "channel_id": "throttle_pct",
              "accepted_source_channel_ids": [
                "throttle_pct",
                "throttle_01",
                "Throttle"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:long_accel",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "long_accel",
              "accepted_source_channel_ids": [
                "long_accel",
                "LongAccel"
              ]
            }
          ],
          "minimum_alternatives": 1
        },
        {
          "requirement_id": "support_channel:rear_wheel_speed_relationship",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "lr_wheel_speed",
              "accepted_source_channel_ids": [
                "lr_wheel_speed",
                "lr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "LRspeed"
              ]
            },
            {
              "channel_id": "rr_wheel_speed",
              "accepted_source_channel_ids": [
                "rr_wheel_speed",
                "rr_speed",
                "rear_wheel_speed_mismatch",
                "rear_wheel_speed_mismatch_raw",
                "rear_wheel_speed_mismatch_corrected",
                "RRspeed"
              ]
            }
          ],
          "minimum_alternatives": 2
        },
        {
          "requirement_id": "support_channel:yaw_rate",
          "evidence_layer_ids": [
            "vehicle_response"
          ],
          "alternatives": [
            {
              "channel_id": "yaw_rate",
              "accepted_source_channel_ids": [
                "yaw_rate",
                "YawRate"
              ]
            }
          ],
          "minimum_alternatives": 1
        }
      ],
      "focus_artifact_prefix": "p35.focus.tire_demand:"
    }
  ]
} as const;

export type P35RuntimeMechanismTrust = (typeof p35RuntimeTrustManifest.mechanisms)[number];
