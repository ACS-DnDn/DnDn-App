export type AuthRole = 'leader' | 'user' | 'auditor';

export interface Company {
  name: string;
  logoUrl: string;
  logoDarkUrl: string;
}

export interface Session {
  id: string;
  name: string;
  email: string;
  role: string;
  position: string | null;
  auth: AuthRole;
  company: Company;
  createdAt: string | null;
}
