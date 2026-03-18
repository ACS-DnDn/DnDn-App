export type AuthRole = 'leader' | 'user' | 'auditor';

export interface Company {
  name: string;
  logoUrl: string;
  logoDarkUrl: string;
}

export interface Session {
  name: string;
  role: string;
  auth: AuthRole;
  company: Company;
}
