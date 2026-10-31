export type GrievanceCategory =
  | 'ROAD_BRIDGE_DAMAGE'
  | 'WATER_LEAK'
  | 'POLLUTION'
  | 'ELECTRICAL_GRID'
  | 'SANITATION_WASTE';

export type GrievanceSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type GrievanceStatus = 'TRIAGED' | 'IN_PROGRESS' | 'RESOLVED' | 'REJECTED';

export interface GrievanceTimelineItem {
  id?: string;
  status: GrievanceStatus;
  remarks: string;
  proof_url?: string | null;
  timestamp: string;
}

export interface GrievanceTicketDto {
  id: string;
  ticket_number: string;
  category: GrievanceCategory;
  description: string;
  voice_transcript?: string | null;
  media_urls: string[];
  latitude: number;
  longitude: number;
  address_label?: string | null;
  severity: GrievanceSeverity;
  severity_score: number;
  ai_triage_summary: string;
  routed_department: {
    id?: string;
    code: string;
    name: string;
  };
  duplicate_of_id?: string | null;
  upvote_count: number;
  status: GrievanceStatus;
  sla_deadline: string;
  resolved_at?: string | null;
  resolution_proof_urls: string[];
  timeline: GrievanceTimelineItem[];
  created_at: string;
}

export interface DepartmentScorecardDto {
  department_code: string;
  department_name: string;
  total_tickets: number;
  resolved_tickets: number;
  sla_compliance_pct: number;
  avg_resolution_hours: number;
  critical_open_count: number;
}

export interface PublicDashboardDto {
  kpis: {
    total_tickets: number;
    resolved_percentage: number;
    sla_breached_count: number;
    avg_resolution_hours: number;
  };
  department_scorecards: DepartmentScorecardDto[];
  map_markers: GrievanceTicketDto[];
}
