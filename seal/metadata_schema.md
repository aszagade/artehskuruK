# Enterprise Metadata Specification

This specification defines the metadata fields required for every knowledge asset in KURUKSHETRA. These fields enable proper governance, traceability, and retrieval of organizational knowledge.

## Fields

### document_id
- **Purpose**: Unique identifier for the knowledge asset across all systems
- **Datatype**: String (UUID recommended)
- **Example**: `doc-550e8400-e29b-41d4-a716-446655440000`

### title
- **Purpose**: Human-readable name or description of the document/asset
- **Datatype**: String
- **Example**: `G3 RMS Installation Process for Opera Cloud Agent`

### team_owner
- **Purpose**: Identifies which organizational team owns this knowledge asset
- **Datatype**: String (enum: Service Delivery, Support, Operations, Revenue, QA, Shared Systems)
- **Example**: `Service Delivery`

### product
- **Purpose**: The IDeaS product or solution this asset relates to
- **Datatype**: String
- **Example**: `G3 RMS`

### system
- **Purpose**: Specific system component or module referenced in the asset
- **Datatype**: String
- **Example**: `Opera Cloud Agent`

### document_type
- **Purpose**: Classification of the knowledge asset type
- **Datatype**: String (enum: Process Guide, Troubleshooting, Configuration, API Reference, Best Practice)
- **Example**: `Process Guide`

### visibility
- **Purpose**: Access control level for the knowledge asset
- **Datatype**: String (enum: Public, Internal, Confidential, Restricted)
- **Example**: `Internal`

### confidence
- **Purpose**: Quality assessment of the knowledge asset content
- **Datatype**: Integer (0-100)
- **Example**: `85`

### version
- **Purpose**: Version identifier for tracking changes over time
- **Datatype**: String (semver recommended)
- **Example**: `1.2.3`

### last_updated
- **Purpose**: Timestamp of the most recent modification
- **Datatype**: ISO 8601 datetime string
- **Example**: `2025-08-22T10:30:45Z`

### source_path
- **Purpose**: File system or storage path to the original asset
- **Datatype**: String
- **Example**: `/knowledge/General_Documents/G3_RMS_Installation_Process.pdf`

### related_tags
- **Purpose**: Keywords or tags for improved search and categorization
- **Datatype**: Array of strings
- **Example**: `["G3", "RMS", "Opera", "Installation", "Cloud"]`