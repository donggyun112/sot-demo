import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import ko from "./ko.json";

export const LOCALE_KEY = "sot.locale";

const stored =
  typeof localStorage === "undefined" ? null : localStorage.getItem(LOCALE_KEY);

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ko: { translation: ko } },
  lng: stored === "ko" ? "ko" : "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (lng) => {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(LOCALE_KEY, lng);
  document.documentElement.lang = lng;
});

export default i18n;
