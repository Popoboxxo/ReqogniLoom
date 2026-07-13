import { apiClient } from "./client";
import type { AttributeVisibilityConfig } from "../context/EntityTypeContext";

export const attributeVisibilityApi = {
  /** Get all attribute visibility configs for the tenant */
  list: async (): Promise<AttributeVisibilityConfig[]> => {
    return apiClient.get<AttributeVisibilityConfig[]>(
      `/attribute-visibility-configs/`
    );
  },

  /** Upsert/Bulk update configs */
  upsert: async (
    configs: AttributeVisibilityConfig[]
  ): Promise<AttributeVisibilityConfig[]> => {
    return apiClient.post<AttributeVisibilityConfig[]>(
      `/attribute-visibility-configs/bulk_update/`,
      configs
    );
  },
};
