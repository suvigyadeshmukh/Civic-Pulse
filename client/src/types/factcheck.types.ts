export type FactCheckVerdict =
  | 'VERIFIED_TRUE'
  | 'MISLEADING'
  | 'FALSE_CLAIM'
  | 'SYNTHETIC_OR_MANIPULATED'
  | 'UNVERIFIED';

export type C2paStatus =
  | 'MANIFEST_VALID'
  | 'MANIFEST_TAMPERED'
  | 'MANIFEST_MISSING';

export interface AuthenticityAnalysisDto {
  c2pa_status: C2paStatus;
  c2pa_issuer?: string | null;
  is_deepfake_suspected: boolean;
  synthetic_probability: number;
  ela_heatmap_url?: string | null;
  technical_findings: string[];
}

export interface EvidenceCitationDto {
  source_authority: string;
  canonical_fact: string;
  reference_url: string;
  similarity_score: number;
}

export interface ProvenanceNodeDto {
  stage: string;
  label: string;
  status: 'VERIFIED' | 'MANIPULATED' | 'UNVERIFIED';
  timestamp?: string;
}

export interface ForensicAuditReportDto {
  audit_id: string;
  claim_id?: string;
  claim_text: string;
  source_url?: string | null;
  media_type: 'TEXT_ONLY' | 'IMAGE' | 'VIDEO' | 'AUDIO';
  media_file_url?: string | null;
  verdict: FactCheckVerdict;
  confidence_score: number;
  credibility_rating: number;
  authenticity_analysis: AuthenticityAnalysisDto;
  evidence_citations: EvidenceCitationDto[];
  provenance_nodes: ProvenanceNodeDto[];
  narrative_summary: string;
  created_at: string;
}
