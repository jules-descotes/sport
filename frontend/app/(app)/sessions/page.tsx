import { redirect } from "next/navigation";

/** L'historique est passé dans Surf le 13/09 : tout ce qui touche à l'eau
 *  entre par la même porte. Les fiches `/sessions/{id}`, elles, ne bougent
 *  pas — le raccourci iPhone ouvre `/sessions/{id}/noter`. */
export default function SessionsPage() {
  redirect("/surf/sessions");
}
