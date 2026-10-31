import type { RegionalLanguageCode } from './common.types';

export type PolicyDocType =
  | 'GOVT_NOTIFICATION'
  | 'WELFARE_SCHEME'
  | 'MUNICIPAL_LAW';

export type PolicyTargetGroup = 'CITIZEN' | 'SMALL_BUSINESS' | 'BOTH';

export type EligibilityVerdict = 'ELIGIBLE' | 'INELIGIBLE' | 'PARTIAL_MATCH';

export interface PolicySummaryDto {
  id: string;
  title: string;
  reference_code: string;
  doc_type: PolicyDocType;
  issuing_body: string;
  target_group: PolicyTargetGroup;
  source_pdf_url: string;
  status: string;
  clause_count: number;
  published_date?: string | null;
  created_at: string;
}

export interface RightBenefitItem {
  headline: string;
  detail: string;
  citation: string;
}

export interface EligibilityCriterionEval {
  rule: string;
  citizen_value: string;
  passed: boolean;
  citation: string;
}

export interface PolicyExplainerDto {
  explainer_id: string;
  policy_id: string;
  language_code: RegionalLanguageCode;
  persona_type: 'CITIZEN' | 'SMALL_BUSINESS';
  eligibility_status: EligibilityVerdict;
  plain_language_summary: string;
  rights_and_benefits: RightBenefitItem[];
  eligibility_evaluation: EligibilityCriterionEval[];
  real_world_impacts: string[];
  audio_explainer_url?: string | null;
  audio_duration_sec: number;
  created_at?: string;
}
