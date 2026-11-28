import { z } from "zod";
import { learningModelCatalogSchema } from "@shadowclone/learning/browser";
import { request } from "./api";
import { actionButton, perform } from "./actions";
import { create, notice, reportError, select } from "./dom";

export function initializeLearningModels(): void {
  let catalog: z.infer<typeof learningModelCatalogSchema> | null = null;
  actionButton({ id: "load-models", action: async () => {
    catalog = await request({ path: "/api/learning-models", schema: learningModelCatalogSchema });
    const control = select("learning-model");
    const placeholder = create({ tag: "option", text: "Choose a configured model" });
    placeholder.value = "";
    placeholder.disabled = true;
    placeholder.selected = !catalog.choices.some(choice => choice.engine === catalog?.selected.engine && choice.model === catalog?.selected.model);
    control.replaceChildren(placeholder, ...catalog.choices.map((choice, index) => {
      const option = create({ tag: "option", text: choice.name });
      option.value = String(index);
      option.selected = choice.engine === catalog?.selected.engine && choice.model === catalog?.selected.model;
      return option;
    }));
    if (catalog.choices.length === 0) notice({ message: "Configure a model in your coding harness, then refresh models." });
  }});
  select("learning-model").addEventListener("change", () => {
    const value = select("learning-model").value;
    if (value === "") return;
    const choice = catalog?.choices[Number(value)];
    if (!choice) return;
    perform(async () => {
      await request({ path: "/api/learning-model", schema: z.object({ saved: z.boolean() }), body: { engine: choice.engine, model: choice.model } });
      notice({ message: "Saved your learning model. Session learning follows the session model unless overridden.", success: true });
    }).catch(reportError);
  });
}
