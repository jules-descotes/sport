// IndexedDB n'existe pas dans Node : `fake-indexeddb/auto` en installe une
// implémentation conforme sur l'objet global, avant tout import de la file.
import "fake-indexeddb/auto";
