export type BureaucracyServiceCode =
  | 'SCHOLARSHIP_RENEWAL'
  | 'MSME_LICENSE'
  | 'WELFARE_SUBSIDY';

export type AgentRunStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'WAITING_FOR_HITL'
  | 'COMPLETED'
  | 'FAILED';

export type HitlObstacleType = 'OTP' | 'CAPTCHA';

export interface AgentActionStepDto {
  step_number: number;
  action: string;
  detail: string;
  selector_target?: string | null;
  screenshot_url?: string | null;
  status: string;
  timestamp: string;
}

export interface AgentRunStartDto {
  run_id: string;
  status: AgentRunStatus;
  ws_channel: string;
}

export interface AgentRunDetailDto {
  run_id: string;
  service_code: BureaucracyServiceCode;
  portal_url: string;
  status: AgentRunStatus;
  hitl_obstacle_type?: HitlObstacleType | null;
  hitl_prompt_message?: string | null;
  hitl_screenshot_url?: string | null;
  tracking_receipt_id?: string | null;
  receipt_pdf_url?: string | null;
  error_detail?: string | null;
  steps: AgentActionStepDto[];
  created_at: string;
  completed_at?: string | null;
}

export interface WsAgentEvent {
  event_type:
    | 'STEP_UPDATE'
    | 'AGENT_HITL_REQUIRED'
    | 'AGENT_COMPLETED'
    | 'AGENT_FAILED';
  run_id: string;
  step_number?: number;
  action?: string;
  detail?: string;
  obstacle_type?: HitlObstacleType;
  prompt_message?: string;
  screenshot_url?: string | null;
  tracking_receipt_id?: string | null;
  receipt_pdf_url?: string | null;
  timestamp: string;
}
