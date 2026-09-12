export type Discipline = "surf" | "foil" | "longboard";

export interface Profile {
  display_name: string | null;
  height_m: number | null;
  weight_kg: number | null;
  level: string | null;
  disciplines: Discipline[];
  timezone: string;
}

export interface User {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
  profile: Profile | null;
}
