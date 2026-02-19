# DynamoDB GSI Implementation

## Environment

| Setting | Value |
|---|---|
| **AWS Account** | EvolentConnectProd (4900-0463-8518) |
| **AWS Region** | `us-east-1` |
| **Table Name** | `ConnectViewData` |

## GSI to Create

| Setting | Value |
|---|---|
| **GSI Name** | `Channel-InitiationTimestamp-index` |
| **Partition Key (PK)** | `Channel` (String) |
| **Sort Key (SK)** | `InitiationTimestamp` (String) |
| **Projection** | `ALL` |
| **Capacity Mode** | Match existing table |

## Task

Create this GSI on the `ConnectViewData` table. No other changes needed.
