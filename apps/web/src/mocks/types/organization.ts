export interface OrgMember {
  id: string;
  name: string;
  rank: string;
}

export interface OrgDept {
  dept: string;
  members: OrgMember[];
}
