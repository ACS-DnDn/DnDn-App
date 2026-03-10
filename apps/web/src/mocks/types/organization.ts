export interface OrgMember {
  name: string;
  rank: string;
}

export interface OrgDept {
  dept: string;
  members: OrgMember[];
}
