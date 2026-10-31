import type { RegionalLanguageCode } from './common.types';

export type UserRole = 'CITIZEN' | 'BUSINESS_OWNER' | 'OFFICER' | 'ADMIN';

export interface UserDto {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  preferred_language: RegionalLanguageCode;
  department_id?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
  preferred_language: RegionalLanguageCode;
  department_code?: string | null;
}

export interface AuthResponseDto {
  access_token: string;
  token_type: string;
  user: UserDto;
}

export interface PiiSecretPayload {
  national_id: string;
  dob: string;
  bank_iban: string;
  phone_number: string;
  portal_pin: string;
}

export interface PublicProfilePayload {
  state: string;
  annual_income: number;
  occupation: string;
  category: string;
  is_msme: boolean;
  education_level: string;
}

export interface CitizenVaultUpsertRequest {
  pii_secret: PiiSecretPayload;
  public_profile: PublicProfilePayload;
  document_urls: string[];
}

export interface CitizenVaultDto {
  vault_id: string;
  user_id: string;
  pii_secret: PiiSecretPayload;
  public_profile: PublicProfilePayload;
  document_urls: string[];
  updated_at: string;
}

export interface DepartmentDto {
  id: string;
  code: string;
  name: string;
  categories_handled: string[];
  sla_hours_critical: number;
  sla_hours_high: number;
  sla_hours_medium: number;
  sla_hours_low: number;
  contact_email: string;
}
