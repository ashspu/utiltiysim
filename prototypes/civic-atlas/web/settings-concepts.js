import {renderPhysicalSliderForm,configurationFormSchema} from './physical-slider-form.mjs';
const bundledCatalog = {
  "configurationVersion": "physical-setup/4",
  "schemas": {
    "world": {
      "type": "object",
      "properties": {
        "weather": {
          "type": "object",
          "title": "Daily weather",
          "properties": {
            "winter_mean_c": {
              "type": "number",
              "title": "Winter average",
              "default": 2.0,
              "x-unit": "\u00b0C",
              "x-control": {
                "kind": "slider",
                "displayMinimum": -30,
                "displayMaximum": 20,
                "step": 0.5,
                "labels": [
                  "Colder winters",
                  "Milder winters"
                ],
                "effect": "Changes daily weather and temperature-sensitive demand.",
                "allowExactInput": true,
                "referenceValue": 2.0,
                "referenceLabel": "Engine starting value",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "summer_mean_c": {
              "type": "number",
              "title": "Summer average",
              "default": 26.0,
              "x-unit": "\u00b0C",
              "x-control": {
                "kind": "slider",
                "displayMinimum": 0,
                "displayMaximum": 45,
                "step": 0.5,
                "labels": [
                  "Cooler summers",
                  "Hotter summers"
                ],
                "effect": "Changes daily weather and cooling-sensitive demand.",
                "allowExactInput": true,
                "referenceValue": 26.0,
                "referenceLabel": "Engine starting value",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "daily_weather_spread_c": {
              "type": "number",
              "title": "Daily variation",
              "default": 6.0,
              "x-unit": "\u00b0C",
              "minimum": 0,
              "x-control": {
                "kind": "slider",
                "displayMinimum": 0,
                "displayMaximum": 20,
                "step": 0.5,
                "labels": [
                  "Steadier weather",
                  "More variable weather"
                ],
                "effect": "Changes day-to-day temperature variation.",
                "allowExactInput": true,
                "referenceValue": 6.0,
                "referenceLabel": "Engine starting value",
                "severityBasis": "relative-to-starting-assumption"
              }
            }
          }
        },
        "meters": {
          "type": "object",
          "title": "Meter condition",
          "properties": {
            "annual_meter_failure": {
              "type": "number",
              "title": "Annual base failure probability",
              "default": 0.015,
              "x-unit": "",
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "displayMinimum": 0,
                "displayMaximum": 0.2,
                "step": 0.001,
                "labels": [
                  "More reliable meters",
                  "More frequent failures"
                ],
                "effect": "Base annual failure probability; meter age further affects failures.",
                "allowExactInput": true,
                "referenceValue": 0.015,
                "referenceLabel": "Engine starting value",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "annual_meter_drift": {
              "type": "number",
              "title": "Annual drift probability",
              "default": 0.01,
              "x-unit": "",
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "displayMinimum": 0,
                "displayMaximum": 0.2,
                "step": 0.001,
                "labels": [
                  "Less drift",
                  "More drift"
                ],
                "effect": "Controls how often healthy meters develop measurement drift.",
                "allowExactInput": true,
                "referenceValue": 0.01,
                "referenceLabel": "Engine starting value",
                "severityBasis": "relative-to-starting-assumption"
              }
            }
          }
        }
      }
    },
    "physical": {
      "type": "object",
      "title": "Physical and customer assumptions",
      "additionalProperties": false,
      "properties": {
        "customerContacts": {
          "type": "object",
          "title": "Customer reactions to physical problems",
          "additionalProperties": false,
          "properties": {
            "active": {
              "type": "boolean",
              "title": "Enable this world behavior",
              "default": false,
              "x-control": {
                "kind": "toggle"
              }
            },
            "noticeProbabilityPerDay": {
              "type": "number",
              "title": "Daily chance of noticing an experienced problem",
              "default": 0.5,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "probability",
                "allowExactInput": true,
                "referenceValue": 0.5,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Less likely to contact",
                  "More likely to contact"
                ],
                "effect": "Higher values can produce earlier contact intentions after experienced supply loss or visible overflow.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "deliveryDelaySeconds": {
              "type": "integer",
              "title": "Delay before a customer contact becomes available",
              "default": 86400,
              "minimum": 0,
              "maximum": 31622400,
              "x-control": {
                "kind": "slider",
                "step": 3600,
                "unit": "seconds",
                "allowExactInput": true,
                "referenceValue": 86400,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Sooner",
                  "Later"
                ],
                "effect": "Delays the customer contact evidence; this is not a call-centre processing queue.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "repeatAfterDays": {
              "type": "integer",
              "title": "Days before another contact about the same episode",
              "default": 3,
              "minimum": 1,
              "maximum": 365,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "days",
                "allowExactInput": true,
                "referenceValue": 3,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More frequent repeats",
                  "Less frequent repeats"
                ],
                "effect": "Shorter intervals permit more frequent repeat contacts while the experienced problem persists.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "maxContacts": {
              "type": "integer",
              "title": "Maximum contacts per experienced episode",
              "default": 3,
              "minimum": 1,
              "maximum": 10,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "contacts",
                "allowExactInput": true,
                "referenceValue": 3,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Fewer repeats",
                  "More repeats"
                ],
                "effect": "Caps repeated customer contact intentions for one episode.",
                "severityBasis": "relative-to-starting-assumption"
              }
            }
          }
        },
        "householdFinance": {
          "type": "object",
          "title": "Household finances and payment behavior",
          "additionalProperties": false,
          "properties": {
            "enabled": {
              "type": "boolean",
              "title": "Configure occupied residential households",
              "default": false,
              "x-control": {
                "kind": "toggle"
              }
            },
            "cashCents": {
              "type": "integer",
              "title": "Starting household cash",
              "default": 200000,
              "minimum": 0,
              "maximum": 100000000,
              "x-control": {
                "kind": "slider",
                "step": 10000,
                "unit": "minor currency units",
                "allowExactInput": true,
                "referenceValue": 200000,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Smaller cash cushion",
                  "Larger cash cushion"
                ],
                "effect": "Sets each eligible household's initial cash; it is not an enterprise account balance.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "essentialReserveCents": {
              "type": "integer",
              "title": "Cash protected from utility-payment intentions",
              "default": 50000,
              "minimum": 0,
              "maximum": 100000000,
              "x-control": {
                "kind": "slider",
                "step": 5000,
                "unit": "minor currency units",
                "allowExactInput": true,
                "referenceValue": 50000,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Less protected cash",
                  "More protected cash"
                ],
                "effect": "Higher reserves protect more household cash and can reduce money available for utility payments.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "maxPaymentCents": {
              "type": "integer",
              "title": "Maximum amount per payment intention",
              "default": 50000,
              "minimum": 1,
              "maximum": 100000000,
              "x-control": {
                "kind": "slider",
                "step": 1000,
                "unit": "minor currency units",
                "allowExactInput": true,
                "referenceValue": 50000,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Smaller payments",
                  "Larger payments"
                ],
                "effect": "Caps a household payment intention after a trusted invoice has been received.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "paymentProbability": {
              "type": "number",
              "title": "Daily payment attempt probability",
              "default": 0.75,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "probability",
                "allowExactInput": true,
                "referenceValue": 0.75,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Less likely to attempt",
                  "More likely to attempt"
                ],
                "effect": "Applies only to received known obligations with available cash; does not create bills or post enterprise payments.",
                "severityBasis": "relative-to-starting-assumption"
              }
            }
          }
        },
        "householdCashflow": {
          "type": "object",
          "title": "Recurring household income and essential expenses",
          "additionalProperties": false,
          "properties": {
            "enabled": {
              "type": "boolean",
              "title": "Enable recurring cashflow (requires household finances)",
              "default": false,
              "x-control": {
                "kind": "toggle"
              }
            },
            "incomeCents": {
              "type": "integer",
              "title": "Income per occurrence",
              "default": 300000,
              "minimum": 0,
              "maximum": 100000000,
              "x-control": {
                "kind": "slider",
                "step": 10000,
                "unit": "minor currency units",
                "allowExactInput": true,
                "referenceValue": 300000,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Less income",
                  "More income"
                ],
                "effect": "Adds income on each configured interval, starting on the world start date.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "incomeIntervalDays": {
              "type": "integer",
              "title": "Income interval",
              "default": 30,
              "minimum": 1,
              "maximum": 366,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "UTC days",
                "allowExactInput": true,
                "referenceValue": 30,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More frequent",
                  "Less frequent"
                ],
                "effect": "Uses a fixed day interval, not calendar months.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "expenseCents": {
              "type": "integer",
              "title": "Essential expenses per occurrence",
              "default": 240000,
              "minimum": 0,
              "maximum": 100000000,
              "x-control": {
                "kind": "slider",
                "step": 10000,
                "unit": "minor currency units",
                "allowExactInput": true,
                "referenceValue": 240000,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Lower expense pressure",
                  "Higher expense pressure"
                ],
                "effect": "Consumes household cash for non-utility essentials; unfunded expense is recorded.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "expenseIntervalDays": {
              "type": "integer",
              "title": "Essential-expense interval",
              "default": 30,
              "minimum": 1,
              "maximum": 366,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "UTC days",
                "allowExactInput": true,
                "referenceValue": 30,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More frequent",
                  "Less frequent"
                ],
                "effect": "Shorter intervals create more frequent household expense pressure.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "insufficientCashPolicy": {
              "type": "string",
              "title": "When essential expenses exceed available cash",
              "enum": [
                "available-cash",
                "all-or-nothing"
              ],
              "default": "available-cash",
              "x-control": {
                "kind": "select",
                "optionLabels": {
                  "available-cash": "Spend available cash; record the unpaid remainder",
                  "all-or-nothing": "Skip an unaffordable expense; record the full amount unpaid"
                }
              }
            }
          }
        },
        "meterChannels": {
          "type": "object",
          "title": "Meter technology and collection",
          "additionalProperties": false,
          "properties": {
            "enabled": {
              "type": "boolean",
              "title": "Apply meter technology and collection assumptions",
              "default": false,
              "x-control": {
                "kind": "toggle"
              }
            },
            "amiPercent": {
              "type": "number",
              "title": "AMI share",
              "default": 80,
              "minimum": 0,
              "maximum": 100,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "percent",
                "allowExactInput": true,
                "referenceValue": 80,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Smaller share",
                  "Larger share"
                ],
                "effect": "Shares must total 100%. Assignments preserve existing meter identities.",
                "severityBasis": "descriptive"
              }
            },
            "amrPercent": {
              "type": "number",
              "title": "AMR share",
              "default": 15,
              "minimum": 0,
              "maximum": 100,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "percent",
                "allowExactInput": true,
                "referenceValue": 15,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Smaller share",
                  "Larger share"
                ],
                "effect": "Shares must total 100%. Assignments preserve existing meter identities.",
                "severityBasis": "descriptive"
              }
            },
            "manualPercent": {
              "type": "number",
              "title": "MANUAL share",
              "default": 5,
              "minimum": 0,
              "maximum": 100,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "percent",
                "allowExactInput": true,
                "referenceValue": 5,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Smaller share",
                  "Larger share"
                ],
                "effect": "Shares must total 100%. Assignments preserve existing meter identities.",
                "severityBasis": "descriptive"
              }
            },
            "amrReadIntervalDays": {
              "type": "integer",
              "title": "AMR collection interval",
              "default": 7,
              "minimum": 1,
              "maximum": 366,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "UTC days",
                "allowExactInput": true,
                "referenceValue": 7,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More frequent",
                  "Less frequent"
                ],
                "effect": "Collects an accumulated measured interval on a fixed schedule; does not configure crews or routing.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "manualReadIntervalDays": {
              "type": "integer",
              "title": "Manual collection interval",
              "default": 30,
              "minimum": 1,
              "maximum": 366,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "UTC days",
                "allowExactInput": true,
                "referenceValue": 30,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More frequent",
                  "Less frequent"
                ],
                "effect": "Collects an accumulated measured interval on a fixed schedule; does not configure crews or routing.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "amiReadSuccess": {
              "type": "number",
              "title": "AMI collection success",
              "default": 0.99,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "probability",
                "allowExactInput": true,
                "referenceValue": 0.99,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More missed collections",
                  "More successful collections"
                ],
                "effect": "Chance a scheduled collection succeeds. A missed collection retains measured accumulation for a later read.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "amrReadSuccess": {
              "type": "number",
              "title": "AMR collection success",
              "default": 0.98,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "probability",
                "allowExactInput": true,
                "referenceValue": 0.98,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More missed collections",
                  "More successful collections"
                ],
                "effect": "Chance a scheduled collection succeeds. A missed collection retains measured accumulation for a later read.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "manualReadSuccess": {
              "type": "number",
              "title": "MANUAL collection success",
              "default": 0.95,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "probability",
                "allowExactInput": true,
                "referenceValue": 0.95,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More missed collections",
                  "More successful collections"
                ],
                "effect": "Chance a scheduled collection succeeds. A missed collection retains measured accumulation for a later read.",
                "severityBasis": "relative-to-starting-assumption"
              }
            }
          },
          "x-control": {
            "kind": "linked-percentages",
            "total": 100,
            "fields": [
              "amiPercent",
              "amrPercent",
              "manualPercent"
            ]
          }
        },
        "housingAge": {
          "type": "object",
          "title": "Housing age and thermal demand",
          "additionalProperties": false,
          "properties": {
            "enabled": {
              "type": "boolean",
              "title": "Apply housing-age scenario to residential premises",
              "default": false,
              "x-control": {
                "kind": "toggle"
              }
            },
            "meanAgeYears": {
              "type": "integer",
              "title": "Central house age",
              "default": 40,
              "minimum": 0,
              "maximum": 200,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "years",
                "allowExactInput": true,
                "referenceValue": 40,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Newer homes",
                  "Older homes"
                ],
                "effect": "Centre of a uniform age distribution, clipped to 0\u2013200 years. This is not a condition rating.",
                "severityBasis": "descriptive"
              }
            },
            "ageSpreadYears": {
              "type": "integer",
              "title": "Age spread either side of the centre",
              "default": 30,
              "minimum": 0,
              "maximum": 200,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "years",
                "allowExactInput": true,
                "referenceValue": 30,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Similar ages",
                  "Varied ages"
                ],
                "effect": "Wider values create a more varied housing stock; clipping can shift the realised mean.",
                "severityBasis": "descriptive"
              }
            },
            "extraThermalDemandPer50Years": {
              "type": "number",
              "title": "Extra thermal demand per 50 years of age",
              "default": 0.25,
              "minimum": 0,
              "maximum": 2,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "fraction",
                "allowExactInput": true,
                "referenceValue": 0.25,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "No age effect",
                  "Stronger age effect"
                ],
                "effect": "Illustrative sensitivity, not a calibrated age-efficiency rule. Scales heating and cooling only.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "retrofittedPercent": {
              "type": "number",
              "title": "Homes with thermal retrofit",
              "default": 0,
              "minimum": 0,
              "maximum": 100,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "percent",
                "allowExactInput": true,
                "referenceValue": 0,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Fewer retrofits",
                  "More retrofits"
                ],
                "effect": "A modeled retrofit removes 75% of the age-related extra thermal demand; a scenario assumption, not a measured standard.",
                "severityBasis": "relative-to-starting-assumption"
              }
            }
          }
        },
        "customerSentiment": {
          "type": "object",
          "title": "Community confidence and customer sentiment",
          "additionalProperties": false,
          "properties": {
            "enabled": {
              "type": "boolean",
              "title": "Enable sentiment feedback",
              "default": false,
              "x-control": {
                "kind": "toggle"
              }
            },
            "initialTrust": {
              "type": "number",
              "title": "Initial trust in the utility",
              "default": 70,
              "minimum": 0,
              "maximum": 100,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "trust points",
                "allowExactInput": true,
                "referenceValue": 70,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Hostile",
                  "Trusting"
                ],
                "effect": "Initial community and household confidence. Lower trust can amplify contact about an experienced problem.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "recoveryDays": {
              "type": "integer",
              "title": "Confidence recovery timescale",
              "default": 30,
              "minimum": 1,
              "maximum": 365,
              "x-control": {
                "kind": "slider",
                "step": 1,
                "unit": "days",
                "allowExactInput": true,
                "referenceValue": 30,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Faster recovery",
                  "Longer memory"
                ],
                "effect": "Each quiet day removes this fraction (1 / days) of frustration. This is gradual recovery, not a fixed expiry.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "experienceImpact": {
              "type": "number",
              "title": "Impact of an experienced service problem",
              "default": 0.08,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "frustration fraction per day",
                "allowExactInput": true,
                "referenceValue": 0.08,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Lower impact",
                  "Higher impact"
                ],
                "effect": "Adds frustration on a day with experienced supply loss or visible overflow; hidden faults and missing readings do not count.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "lateBillImpact": {
              "type": "number",
              "title": "Impact of a bill delivered after its due date",
              "default": 0.1,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "frustration fraction",
                "allowExactInput": true,
                "referenceValue": 0.1,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "Lower impact",
                  "Higher impact"
                ],
                "effect": "Uses actually received invoice evidence once, capped at one impact per household per day. Does not create bills or infer unpaid bills.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "communityInfluence": {
              "type": "number",
              "title": "Community influence on household mood",
              "default": 0.05,
              "minimum": 0,
              "maximum": 1,
              "x-control": {
                "kind": "slider",
                "step": 0.01,
                "unit": "daily influence fraction",
                "allowExactInput": true,
                "referenceValue": 0.05,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "More independent",
                  "Stronger shared reaction"
                ],
                "effect": "Couples household frustration and town mood; public news can spread through this bounded feedback.",
                "severityBasis": "relative-to-starting-assumption"
              }
            },
            "maxContactMultiplier": {
              "type": "number",
              "title": "Maximum contact amplification",
              "default": 2,
              "minimum": 1,
              "maximum": 5,
              "x-control": {
                "kind": "slider",
                "step": 0.1,
                "unit": "multiplier",
                "allowExactInput": true,
                "referenceValue": 2,
                "referenceLabel": "Illustrative starting assumption",
                "labels": [
                  "No amplification",
                  "More contact pressure"
                ],
                "effect": "Raises notice probability and the repeat-contact limit, and shortens repeat spacing for existing experienced problems. Probability stays at most 100%; repeats at most 10 per episode.",
                "severityBasis": "relative-to-starting-assumption"
              }
            }
          }
        }
      }
    }
  },
  "defaults": {
    "schemaVersion": "physical-setup/4",
    "world": {
      "weather": {
        "winter_mean_c": 2.0,
        "summer_mean_c": 26.0,
        "daily_weather_spread_c": 6.0
      },
      "meters": {
        "annual_meter_failure": 0.015,
        "annual_meter_drift": 0.01
      }
    },
    "physical": {
      "customerContacts": {
        "active": false,
        "noticeProbabilityPerDay": 0.5,
        "deliveryDelaySeconds": 86400,
        "repeatAfterDays": 3,
        "maxContacts": 3
      },
      "householdFinance": {
        "enabled": false,
        "cashCents": 200000,
        "essentialReserveCents": 50000,
        "maxPaymentCents": 50000,
        "paymentProbability": 0.75
      },
      "householdCashflow": {
        "enabled": false,
        "incomeCents": 300000,
        "incomeIntervalDays": 30,
        "expenseCents": 240000,
        "expenseIntervalDays": 30,
        "insufficientCashPolicy": "available-cash"
      },
      "meterChannels": {
        "enabled": false,
        "amiPercent": 80,
        "amrPercent": 15,
        "manualPercent": 5,
        "amrReadIntervalDays": 7,
        "manualReadIntervalDays": 30,
        "amiReadSuccess": 0.99,
        "amrReadSuccess": 0.98,
        "manualReadSuccess": 0.95
      },
      "housingAge": {
        "enabled": false,
        "meanAgeYears": 40,
        "ageSpreadYears": 30,
        "extraThermalDemandPer50Years": 0.25,
        "retrofittedPercent": 0
      },
      "customerSentiment": {
        "enabled": false,
        "initialTrust": 70,
        "recoveryDays": 30,
        "experienceImpact": 0.08,
        "lateBillImpact": 0.1,
        "communityInfluence": 0.05,
        "maxContactMultiplier": 2
      }
    }
  },
  "scope": {
    "householdPolicies": "Uniform initial assumptions for occupied residential premises only",
    "currency": "Minor currency units; no currency conversion or enterprise tariff configuration",
    "unsupportedRequiredControls": [],
    "otherEngineControlsPendingHostedAdapters": [
      "dated occupancy changes",
      "infrastructure hazards",
      "network and water faults",
      "development"
    ],
    "sentimentLimits": "Amplifies experienced-service contacts only; financial-contact escalation and news-only inquiries are not yet modeled."
  }
};
const schema=configurationFormSchema(bundledCatalog,bundledCatalog.defaults);
const drafts=new Map(['atlas','seasons','desk'].map(key=>[key,structuredClone(bundledCatalog.defaults)]));let chosen='atlas',form;
function render(){
 document.getElementById('preview').className=`concept-${chosen}`;
 const copy={atlas:['ATLAS CARDS','Make the assumptions yours.'],seasons:['SEASONAL CANVAS','Start with the rhythm of the year.'],desk:['CONTROL DESK','Every assumption, within reach.']}[chosen];
 document.getElementById('concept-kicker').textContent=copy[0];document.getElementById('concept-title').textContent=copy[1];
 form=renderPhysicalSliderForm(document.getElementById('controls'),schema,{defaults:bundledCatalog.defaults,values:drafts.get(chosen),onChange:(values,errors)=>{drafts.set(chosen,{...values,schemaVersion:bundledCatalog.defaults.schemaVersion});document.getElementById('preview-state').textContent=errors.length?'Check highlighted values':'Preview updated';summarize(values);}});
 if(chosen==='desk')document.querySelectorAll('.physical-setting-group').forEach(group=>group.open=true);
 summarize(form.values);
}
function summarize(values){document.getElementById('winter-summary').textContent=`${values.world.weather.winter_mean_c}°C`;document.getElementById('summer-summary').textContent=`${values.world.weather.summer_mean_c}°C`;document.getElementById('values').textContent=JSON.stringify(values,null,2);}
for(const button of document.querySelectorAll('[data-concept]'))button.onclick=()=>{drafts.set(chosen,{...form.values,schemaVersion:bundledCatalog.defaults.schemaVersion});chosen=button.dataset.concept;for(const node of document.querySelectorAll('[data-concept]'))node.setAttribute('aria-pressed',String(node===button));document.getElementById('preview-state').textContent='Independent design preview';render();};
document.getElementById('show-values').onclick=()=>{const node=document.getElementById('values');node.hidden=!node.hidden;};render();