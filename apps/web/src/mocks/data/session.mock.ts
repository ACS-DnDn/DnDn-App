import type { Session } from '../types/session';

export const session: Session = {
  id: 'user-001',
  name: '정지은',
  email: 'jjeong@cslee.io',
  role: '선임연구원',
  position: null,
  auth: 'leader',
  company: {
    name: 'CSLEE.',
    logoUrl: '/mock/logo_real.png',
    logoDarkUrl: '/mock/logo_real.png',
  },
  createdAt: '2024.03.01',
};
