import { redirect } from "next/navigation";

/** Le matos est passé dans Surf le 13/09 : on le choisit en notant une
 *  session, pas en réglant son profil. */
export default function ProfilMatosPage() {
  redirect("/surf/matos");
}
