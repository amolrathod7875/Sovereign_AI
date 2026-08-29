# P&ID Analysis Report

- **Engine:** local Qwen2.5-VL 3B (Q4_K_M) via CUDA llama-server (RTX 4050 6 GB)
- **Source folder:** `D:\Sovereign_AI\PID_Dataset\0__raw_data\sheets\test`
- **Drawings analyzed:** 21
- **Prompt:** structured 12-field P&ID extraction

## Summary Table

| Drawing         | Plant/Process                               | Major Equipment                                                                                                                                                                 | Tags                                                                                                   | Pumps                                                                                                                | Tanks/Vessels                    | HX                             | Compressors            | Valves                                                                                                                                                      | Instruments | Uncertain                            | sec  |
| --------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | -------------------------------- | ------------------------------ | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------ | ---- |
| 0.jpg           | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 12.0 |
| 103.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | HV-1, TV-42                                                                                                                                                 | LT, TC, LC  | some tag numbers partially illegible | 6.6  |
| 11.jpg          | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | N/A                                  | 15.2 |
| 124.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | Centrifugal Pumps, Vacuum Pump, Gear Pump, Screw Pump, Turbine                                                       | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 6.2  |
| 129.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 8.5  |
| 136.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | Positive Displacement, Progressive Cavity, Screw Pump, Gear Pump, Vacuum Pump, Vertical Can Pump, Reciprocating Pump | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 15.8 |
| 145.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 16.6 |
| 148.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | N/A                                  | 8.2  |
| 15.jpg          | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | N/A                                  | 21.7 |
| 151.jpg         | Fractionating Tower                         | Fractionating Tower                                                                                                                                                             | T-10013                                                                                                | P-101                                                                                                                | N/A                              | N/A                            | N/A                    | HV-1, TV-42                                                                                                                                                 | LT, TC, LC  | some tag numbers partially illegible | 16.5 |
| 157.jpg         | Waste Treatment for TCS Production Facility | Rotary Vacuum Filter, Vacuum Pump, Lime Tank, Filtrate Pump                                                                                                                     | N/A                                                                                                    | Filtrate Pump, Lime Circulation Pumps                                                                                | Lime Tank, Lime Circulation Tank | N/A                            | N/A                    | HV-1, TV-42                                                                                                                                                 | Alarm       | some tag numbers partially illegible | 15.3 |
| 158.jpg         | Hydrogen Production System                  | Hydrogen Package, Hydrogen Compressor, Hydrogen Receiver, Hydrogen Reducer, Loading Station, Transfer Tank, Feed Heater, Flushed Bed Reactor, Hydrogen Super Heater, Evaporator | X-1003, X-1002, X-1001, V-1001, V-1002, V-1003, V-1004, H-1001, H-1002, H-1003, H-1004, E-1005, E-1006 | P-1001, P-1002                                                                                                       | ~60 G-* tags, mostly vessels     | H-1001, H-1002, H-1003, H-1004 | C-1001, C-1002, C-1003 | HV-1, TV-42, V-1001, V-1002, V-1003, V-1004, H-1001, H-1002, H-1003, H-1004                                                                                 | LT, TC, LC  | some tag numbers partially illegible | 17.7 |
| 159.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | 30-P104A/B                                                                                                           | N/A                              | 30-E107, 30-E109, 30-E110      | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 12.2 |
| 176.jpg         | N/A                                         | P-1001, P-1002, P-1003, R-1001, R-1002                                                                                                                                          | N/A                                                                                                    | P-1001, P-1002, P-1003                                                                                               | R-1001, R-1002                   | N/A                            | N/A                    | HV-1, TV-42                                                                                                                                                 | LT, TC, LC  | some tag numbers partially illegible | 13.5 |
| 188.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | Gate valves, Globe valves, Angle valves, Ball valves, Plug valves, Butterfly valves, Check valves, Diaphragm valves, Safety relief, Quarter turn, Equipment | N/A         | some tag numbers partially illegible | 8.2  |
| 192.jpg         | N/A                                         | N/A                                                                                                                                                                             | D, XXX, F, F, N/A, N/A, N/A, N/A, N/A                                                                  | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 16.5 |
| 194.jpg         | Grit Washer / Grit Classifier               | Grit washer, grit classifier                                                                                                                                                    | GWA-51-371, GCA-51-376                                                                                 | P-101                                                                                                                | N/A                              | N/A                            | N/A                    | HV-1, TV-42                                                                                                                                                 | LT, TC, LC  | some tag numbers partially illegible | 17.6 |
| 194_resized.jpg | Grit Washer / Grit Classifier               | Grit washer, grit classifier                                                                                                                                                    | GWA-51-371, GCA-51-376                                                                                 | P-101                                                                                                                | N/A                              | N/A                            | N/A                    | HV-1, TV-42                                                                                                                                                 | LT, TC, LC  | some tag numbers partially illegible | 5.5  |
| 196.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | N/A                                  | 19.9 |
| 216.jpg         | Desiccant Vessel                            | Desiccant Vessel                                                                                                                                                                | V310, V315                                                                                             | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | HV-310, TV-315                                                                                                                                              | LT, TC, LC  | some tag numbers partially illegible | 11.3 |
| 233.jpg         | N/A                                         | N/A                                                                                                                                                                             | N/A                                                                                                    | N/A                                                                                                                  | N/A                              | N/A                            | N/A                    | N/A                                                                                                                                                         | N/A         | some tag numbers partially illegible | 12.7 |

## Per-Drawing Details

### 1. 0.jpg  _(12.0 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 2. 103.jpg  _(6.6 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** HV-1, TV-42
- **Instruments:** LT, TC, LC
- **Process Flow:** influent -> grit washer -> grit classifier -> outflow
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "HV-1, TV-42", "INSTRUMENTS": "LT, TC, LC", "PROCESS_FLOW": "influent -> grit washer -> grit classifier -> outflow", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 3. 11.jpg  _(15.2 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** N/A

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "Anti Surge Controller, Anti Surge Valve, Pressure Controller, Flow Controller, Temperature Controller, Level Controller, Driver Motor, Compressor, AfterCooler", "EQUIPMENT_TAGS": "ASC, ASV, PC, FC, TC, LC, M, M, M", "PUMPS": "N/A", "TANKS_VESSELS": "Suction KOD", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "RV, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO, CSO,
```

</details>

### 4. 124.jpg  _(6.2 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** Centrifugal Pumps, Vacuum Pump, Gear Pump, Screw Pump, Turbine
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "Centrifugal Pumps, Vacuum Pump, Gear Pump, Screw Pump, Turbine", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 5. 129.jpg  _(8.5 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 6. 136.jpg  _(15.8 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** Positive Displacement, Progressive Cavity, Screw Pump, Gear Pump, Vacuum Pump, Vertical Can Pump, Reciprocating Pump
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "Positive Displacement, Progressive Cavity, Screw Pump, Gear Pump, Vacuum Pump, Vertical Can Pump, Reciprocating Pump", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 7. 145.jpg  _(16.6 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 8. 148.jpg  _(8.2 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** N/A

<details><summary>Raw model output</summary>

```
{
  "DRAWING_ID": "N/A",
  "PLANT_PROCESS": "N/A",
  "MAJOR_EQUIPMENT": "N/A",
  "EQUIPMENT_TAGS": "N/A",
  "PUMPS": "N/A",
  "TANKS_VESSELS": "N/A",
  "HEAT_EXCHANGERS": "N/A",
  "COMPRESSORS": "N/A",
  "VALVES": "N/A",
  "INSTRUMENTS": "N/A",
  "PROCESS_FLOW": "N/A",
  "UNCERTAIN": "N/A"
}
```

</details>

### 9. 15.jpg  _(21.7 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** N/A

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "T-1, T-2, T-3, T-4, T-5, T-6, T-7", "EQUIPMENT_TAGS": "M-1, M-2, XIC-201, XIC-202, XIC-203, XIC-204, LSH-205, LSH-501, LSH-502, LSH-503, LSH-504, LSH-505, LSH-506, LSH-507, LSH-508, LSH-509, LSH-501, LSH-502, LSH-503, LSH-504, LSH-505, LSH-506, LSH-507, LSH-508, LSH-509, LSH-501, LSH-502, LSH-503, LSH-504, LSH-505, LSH-506, LSH-507, LSH-508, LSH-509, LSH-501, LSH-502, LSH-503, LSH-504, LSH-505, LSH-506, LSH-507, LSH-508, LSH-509, LSH-501, LSH-502, LSH-503, LSH-504, LSH-505, LSH-506, LSH-507, LSH-508, LSH-509, LSH-501, LSH-502, LSH-503, LSH-504, LSH-505, LSH-506, LSH-507, LSH-508, LSH-509, LSH-501, LSH-502, LSH-503, LSH-504, LSH
```

</details>

### 10. 151.jpg  _(16.5 s)_

- **Drawing Id:** T-10013
- **Plant Process:** Fractionating Tower
- **Major Equipment:** Fractionating Tower
- **Equipment Tags:** T-10013
- **Pumps:** P-101
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** HV-1, TV-42
- **Instruments:** LT, TC, LC
- **Process Flow:** influent -> fractionating tower -> outflow
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "T-10013", "PLANT_PROCESS": "Fractionating Tower", "MAJOR_EQUIPMENT": "Fractionating Tower", "EQUIPMENT_TAGS": "T-10013", "PUMPS": "P-101", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "HV-1, TV-42", "INSTRUMENTS": "LT, TC, LC", "PROCESS_FLOW": "influent -> fractionating tower -> outflow", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 11. 157.jpg  _(15.3 s)_

- **Drawing Id:** N/A
- **Plant Process:** Waste Treatment for TCS Production Facility
- **Major Equipment:** Rotary Vacuum Filter, Vacuum Pump, Lime Tank, Filtrate Pump
- **Equipment Tags:** N/A
- **Pumps:** Filtrate Pump, Lime Circulation Pumps
- **Tanks Vessels:** Lime Tank, Lime Circulation Tank
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** HV-1, TV-42
- **Instruments:** Alarm
- **Process Flow:** Crushed Lime -> Lime Tank -> Lime Circulation Pumps -> Filtrate Pump -> Rotary Vacuum Filter -> Filtrate -> Vent Stack Nozzles, Sheet 1 -> Sludge to Landfill
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{
  "DRAWING_ID": "N/A",
  "PLANT_PROCESS": "Waste Treatment for TCS Production Facility",
  "MAJOR_EQUIPMENT": "Rotary Vacuum Filter, Vacuum Pump, Lime Tank, Filtrate Pump",
  "EQUIPMENT_TAGS": "N/A",
  "PUMPS": "Filtrate Pump, Lime Circulation Pumps",
  "TANKS_VESSELS": "Lime Tank, Lime Circulation Tank",
  "HEAT_EXCHANGERS": "N/A",
  "COMPRESSORS": "N/A",
  "VALVES": "HV-1, TV-42",
  "INSTRUMENTS": "Alarm",
  "PROCESS_FLOW": "Crushed Lime -> Lime Tank -> Lime Circulation Pumps -> Filtrate Pump -> Rotary Vacuum Filter -> Filtrate -> Vent Stack Nozzles, Sheet 1 -> Sludge to Landfill",
  "UNCERTAIN": "some tag numbers partially illegible"
}
```

</details>

### 12. 158.jpg  _(17.7 s)_

- **Drawing Id:** X-1003
- **Plant Process:** Hydrogen Production System
- **Major Equipment:** Hydrogen Package, Hydrogen Compressor, Hydrogen Receiver, Hydrogen Reducer, Loading Station, Transfer Tank, Feed Heater, Flushed Bed Reactor, Hydrogen Super Heater, Evaporator
- **Equipment Tags:** X-1003, X-1002, X-1001, V-1001, V-1002, V-1003, V-1004, H-1001, H-1002, H-1003, H-1004, E-1005, E-1006
- **Pumps:** P-1001, P-1002
- **Tanks Vessels:** ~60 G-* tags, mostly vessels
- **Heat Exchangers:** H-1001, H-1002, H-1003, H-1004
- **Compressors:** C-1001, C-1002, C-1003
- **Valves:** HV-1, TV-42, V-1001, V-1002, V-1003, V-1004, H-1001, H-1002, H-1003, H-1004
- **Instruments:** LT, TC, LC
- **Process Flow:** Inlet -> Hydrogen Package -> Hydrogen Compressor -> Hydrogen Receiver -> Hydrogen Reducer -> Loading Station -> Transfer Tank -> Feed Heater -> Flushed Bed Reactor -> Hydrogen Super Heater -> Evaporator -> Outflow
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "X-1003", "PLANT_PROCESS": "Hydrogen Production System", "MAJOR_EQUIPMENT": "Hydrogen Package, Hydrogen Compressor, Hydrogen Receiver, Hydrogen Reducer, Loading Station, Transfer Tank, Feed Heater, Flushed Bed Reactor, Hydrogen Super Heater, Evaporator", "EQUIPMENT_TAGS": "X-1003, X-1002, X-1001, V-1001, V-1002, V-1003, V-1004, H-1001, H-1002, H-1003, H-1004, E-1005, E-1006", "PUMPS": "P-1001, P-1002", "TANKS_VESSELS": "~60 G-* tags, mostly vessels", "HEAT_EXCHANGERS": "H-1001, H-1002, H-1003, H-1004", "COMPRESSORS": "C-1001, C-1002, C-1003", "VALVES": "HV-1, TV-42, V-1001, V-1002, V-1003, V-1004, H-1001, H-1002, H-1003, H-1004", "INSTRUMENTS": "LT, TC, LC", "PROCESS_FLOW": "Inlet -> Hydrogen Package -> Hydrogen Compressor -> Hydrogen Receiver -> Hydrogen Reducer -> Loading Station -> Transfer Tank -> Feed Heater -> Flushed Bed Reactor -> Hydrogen Super Heater -> Evaporator -> Outflow", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 13. 159.jpg  _(12.2 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** 30-P104A/B
- **Tanks Vessels:** N/A
- **Heat Exchangers:** 30-E107, 30-E109, 30-E110
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "30-P104A/B", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "30-E107, 30-E109, 30-E110", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 14. 176.jpg  _(13.5 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** P-1001, P-1002, P-1003, R-1001, R-1002
- **Equipment Tags:** N/A
- **Pumps:** P-1001, P-1002, P-1003
- **Tanks Vessels:** R-1001, R-1002
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** HV-1, TV-42
- **Instruments:** LT, TC, LC
- **Process Flow:** UETHANOLETHANOL -> P-1001 -> R-1001 -> P-1002 -> R-1002 -> P-1003 -> PRODUCT
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "P-1001, P-1002, P-1003, R-1001, R-1002", "EQUIPMENT_TAGS": "N/A", "PUMPS": "P-1001, P-1002, P-1003", "TANKS_VESSELS": "R-1001, R-1002", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "HV-1, TV-42", "INSTRUMENTS": "LT, TC, LC", "PROCESS_FLOW": "UETHANOLETHANOL -> P-1001 -> R-1001 -> P-1002 -> R-1002 -> P-1003 -> PRODUCT", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 15. 188.jpg  _(8.2 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** Gate valves, Globe valves, Angle valves, Ball valves, Plug valves, Butterfly valves, Check valves, Diaphragm valves, Safety relief, Quarter turn, Equipment
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "Gate valves, Globe valves, Angle valves, Ball valves, Plug valves, Butterfly valves, Check valves, Diaphragm valves, Safety relief, Quarter turn, Equipment", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 16. 192.jpg  _(16.5 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** D, XXX, F, F, N/A, N/A, N/A, N/A, N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "D, XXX, F, F, N/A, N/A, N/A, N/A, N/A", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 17. 194.jpg  _(17.6 s)_

- **Drawing Id:** 51Y613
- **Plant Process:** Grit Washer / Grit Classifier
- **Major Equipment:** Grit washer, grit classifier
- **Equipment Tags:** GWA-51-371, GCA-51-376
- **Pumps:** P-101
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** HV-1, TV-42
- **Instruments:** LT, TC, LC
- **Process Flow:** influent -> grit washer -> grit classifier -> outflow
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "51Y613", "PLANT_PROCESS": "Grit Washer / Grit Classifier", "MAJOR_EQUIPMENT": "Grit washer, grit classifier", "EQUIPMENT_TAGS": "GWA-51-371, GCA-51-376", "PUMPS": "P-101", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "HV-1, TV-42", "INSTRUMENTS": "LT, TC, LC", "PROCESS_FLOW": "influent -> grit washer -> grit classifier -> outflow", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 18. 194_resized.jpg  _(5.5 s)_

- **Drawing Id:** 51Y613
- **Plant Process:** Grit Washer / Grit Classifier
- **Major Equipment:** Grit washer, grit classifier
- **Equipment Tags:** GWA-51-371, GCA-51-376
- **Pumps:** P-101
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** HV-1, TV-42
- **Instruments:** LT, TC, LC
- **Process Flow:** influent -> grit washer -> grit classifier -> outflow
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "51Y613", "PLANT_PROCESS": "Grit Washer / Grit Classifier", "MAJOR_EQUIPMENT": "Grit washer, grit classifier", "EQUIPMENT_TAGS": "GWA-51-371, GCA-51-376", "PUMPS": "P-101", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "HV-1, TV-42", "INSTRUMENTS": "LT, TC, LC", "PROCESS_FLOW": "influent -> grit washer -> grit classifier -> outflow", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 19. 196.jpg  _(19.9 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** N/A

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "55Y611", "PLANT_PROCESS": "BWR Train 2 Aerobic Zone", "MAJOR_EQUIPMENT": "BWR Train 2 Aerobic Zone", "EQUIPMENT_TAGS": "VBF-55-423, VBF-55-424, VBF-55-425, VBF-55-426, VBF-55-427, VBF-55-428, VBF-55-429, VBF-55-430, VBF-55-431, VBF-55-432, VBF-55-433, VBF-55-434, VBF-55-435, VBF-55-436, VBF-55-437, VBF-55-438, VBF-55-439, VBF-55-440, VBF-55-441, VBF-55-442, VBF-55-443, VBF-55-444, VBF-55-445, VBF-55-446, VBF-55-447, VBF-55-448, VBF-55-449, VBF-55-450, VBF-55-451, VBF-55-452, VBF-55-453, VBF-55-454, VBF-55-455, VBF-55-456, VBF-55-457, VBF-55-458, VBF-55-459, VBF-55-460, VBF-55-461, VBF-55-462, VBF-55-463, VBF-55-464, VBF-55-465, VBF-55-466, VBF-55-467, VBF-55-468,
```

</details>

### 20. 216.jpg  _(11.3 s)_

- **Drawing Id:** V310_V315
- **Plant Process:** Desiccant Vessel
- **Major Equipment:** Desiccant Vessel
- **Equipment Tags:** V310, V315
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** HV-310, TV-315
- **Instruments:** LT, TC, LC
- **Process Flow:** inlet -> desiccant vessel -> outlet
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "V310_V315", "PLANT_PROCESS": "Desiccant Vessel", "MAJOR_EQUIPMENT": "Desiccant Vessel", "EQUIPMENT_TAGS": "V310, V315", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "HV-310, TV-315", "INSTRUMENTS": "LT, TC, LC", "PROCESS_FLOW": "inlet -> desiccant vessel -> outlet", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>

### 21. 233.jpg  _(12.7 s)_

- **Drawing Id:** N/A
- **Plant Process:** N/A
- **Major Equipment:** N/A
- **Equipment Tags:** N/A
- **Pumps:** N/A
- **Tanks Vessels:** N/A
- **Heat Exchangers:** N/A
- **Compressors:** N/A
- **Valves:** N/A
- **Instruments:** N/A
- **Process Flow:** N/A
- **Uncertain:** some tag numbers partially illegible

<details><summary>Raw model output</summary>

```
{"DRAWING_ID": "N/A", "PLANT_PROCESS": "N/A", "MAJOR_EQUIPMENT": "N/A", "EQUIPMENT_TAGS": "N/A", "PUMPS": "N/A", "TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", "VALVES": "N/A", "INSTRUMENTS": "N/A", "PROCESS_FLOW": "N/A", "UNCERTAIN": "some tag numbers partially illegible"}
```

</details>
