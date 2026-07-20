// Configuration Firebase — À REMPLIR une fois (voir app/README.md, étape 1).
// Ces valeurs ne sont pas secrètes (le SDK web les expose de toute façon) ;
// la sécurité vient des règles Firestore/Storage, pas de ces clés.
export const FIREBASE_CONFIG = {
  apiKey: "AIzaSyDnQwEDgC6SI9FlsifI4Tjbq_jY5DI2KYE",
  authDomain: "africatrip-eea1a.firebaseapp.com",
  projectId: "africatrip-eea1a",
  storageBucket: "africatrip-eea1a.firebasestorage.app",
  messagingSenderId: "301314590575",
  appId: "1:301314590575:web:3b89efb7bbc8a4a95aca9a",
};

// Liste de l'équipage : prénom -> voiture (1 = Hugodouard, 2 = Paul Pot,
// "obs" = observateur). Sert au choix du prénom et à colorer les marqueurs.
export const CREW = {
  Gal: 1, Hugo: 1, Malen: 1, Arthur: 1, Edouard: 1, Younous: 1,
  Paul: 2, Thomas: 2, Jehan: 2, Dorvan: 2,
  Giordano: "obs",
};
