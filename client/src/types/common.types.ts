export type AsyncStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error';

export type RegionalLanguageCode =
  | 'hi-IN'
  | 'ta-IN'
  | 'mr-IN'
  | 'te-IN'
  | 'bn-IN'
  | 'en-IN';

export interface PaginatedMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  meta?: PaginatedMeta | null;
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  field_errors?: Record<string, string>;
  request_id?: string;
}

export interface ApiError {
  status: number;
  code: string;
  message: string;
  fieldErrors: Record<string, string>;
  requestId?: string;
}
