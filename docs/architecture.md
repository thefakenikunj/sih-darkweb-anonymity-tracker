# System Architecture Documentation

This document details the architectural layout, data flow, and core analytical pipeline for the Multi-Source Entity Resolution & Stylometric Analysis Platform.

## System Overview

```text
[ Data Ingestion ] ──> [ Normalization ] ──> [ Feature Extraction ] ──> [ Resolution & Graph ] ──> [ Reporting & UI ]
  (collectors/)          (services/)           (services/)              (services/)               (app.py / network.html)