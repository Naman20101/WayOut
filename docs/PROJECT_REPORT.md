# WAYOUT — project report and submission outline

## Front matter

Add your own school, student name, class, roll number, teacher, academic year, certificate signatures and acknowledgement. These personal or institutional details are intentionally not invented.

## Abstract

WAYOUT is a Python and MySQL-based geospatial decision-support system that combines historical hazard data, infrastructure information and risk-weighted graph routing to recommend lower-risk evacuation paths. Three approximately 15 km study areas demonstrate the pipeline under different evidence conditions. The application compares custom Dijkstra distance and weighted-cost objectives, displays available source layers, integrates NASA SRTM terrain as an additive modifier, and makes incomplete coverage visible. It is an educational prototype, not an emergency service.

## Problem and objectives

The shortest road path may intersect more mapped hazard exposure. A comparison should preserve the same endpoints and transport constraints, expose its assumptions, and avoid implying that an unknown location is safe. The project demonstrates Python programming, SQL, relational design, geospatial processing, graphs, web development and source criticism.

## Architecture

```mermaid
flowchart LR
  A[Official hazard files, NASA SRTM and OSM] --> B[Preserve bytes and provenance]
  B --> C[Crop and transform coordinates]
  C --> D[Build topology and sample hazards + terrain]
  D --> E[(MySQL)]
  F[Leaflet and browser controls] --> G[Flask validation]
  G --> E
  E --> H[Custom Dijkstra in Python]
  H --> I[Distance and risk comparison]
  I --> F
