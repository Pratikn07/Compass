export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  prescient_storage: {
    Tables: {
      decision_records: {
        Row: {
          attention_reasons: string[]
          attention_status: string
          created_at: string
          decision_id: string
          decision_index: number | null
          decision_record_id: string
          execution_mode: string | null
          payload: Json
          run_id: string
          schema_version: number
          strategy_status: string | null
          strategy_type: string | null
          target: string | null
          theme: string | null
          trading_date: string
        }
        Insert: {
          attention_reasons?: string[]
          attention_status?: string
          created_at?: string
          decision_id: string
          decision_index?: number | null
          decision_record_id: string
          execution_mode?: string | null
          payload?: Json
          run_id: string
          schema_version?: number
          strategy_status?: string | null
          strategy_type?: string | null
          target?: string | null
          theme?: string | null
          trading_date: string
        }
        Update: {
          attention_reasons?: string[]
          attention_status?: string
          created_at?: string
          decision_id?: string
          decision_index?: number | null
          decision_record_id?: string
          execution_mode?: string | null
          payload?: Json
          run_id?: string
          schema_version?: number
          strategy_status?: string | null
          strategy_type?: string | null
          target?: string | null
          theme?: string | null
          trading_date?: string
        }
        Relationships: []
      }
      system_health: {
        Row: {
          component: string
          created_at: string
          detail: string | null
          latency_seconds: number | null
          payload: Json
          run_id: string | null
          schema_version: number
          status: string
          system_health_id: string
        }
        Insert: {
          component: string
          created_at?: string
          detail?: string | null
          latency_seconds?: number | null
          payload?: Json
          run_id?: string | null
          schema_version?: number
          status?: string
          system_health_id: string
        }
        Update: {
          component?: string
          created_at?: string
          detail?: string | null
          latency_seconds?: number | null
          payload?: Json
          run_id?: string | null
          schema_version?: number
          status?: string
          system_health_id?: string
        }
        Relationships: []
      }
      watchlist_items: {
        Row: {
          created_at: string
          schema_version: number
          sort_order: number
          theme: string | null
          ticker: string
          watchlist_id: string
          watchlist_item_id: string
        }
        Insert: {
          created_at?: string
          schema_version?: number
          sort_order?: number
          theme?: string | null
          ticker: string
          watchlist_id: string
          watchlist_item_id: string
        }
        Update: {
          created_at?: string
          schema_version?: number
          sort_order?: number
          theme?: string | null
          ticker?: string
          watchlist_id?: string
          watchlist_item_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "watchlist_items_watchlist_id_fkey"
            columns: ["watchlist_id"]
            isOneToOne: false
            referencedRelation: "watchlists"
            referencedColumns: ["watchlist_id"]
          },
        ]
      }
      watchlists: {
        Row: {
          created_at: string
          description: string | null
          name: string
          schema_version: number
          source: string
          updated_at: string
          watchlist_id: string
        }
        Insert: {
          created_at?: string
          description?: string | null
          name: string
          schema_version?: number
          source?: string
          updated_at?: string
          watchlist_id: string
        }
        Update: {
          created_at?: string
          description?: string | null
          name?: string
          schema_version?: number
          source?: string
          updated_at?: string
          watchlist_id?: string
        }
        Relationships: []
      }
      journal_records: {
        Row: {
          created_at: string
          decision_id: string | null
          decision_index: number | null
          duplicate_of_record_id: string | null
          execution_mode: string | null
          journal_record_id: string
          order_id: string | null
          parent_record_id: string | null
          payload: Json
          provider: string | null
          record_type: string
          run_id: string
          schema_version: number
          source: string
          strategy_status: string | null
          strategy_type: string | null
          target: string | null
          theme: string | null
          trading_date: string
        }
        Insert: {
          created_at?: string
          decision_id?: string | null
          decision_index?: number | null
          duplicate_of_record_id?: string | null
          execution_mode?: string | null
          journal_record_id: string
          order_id?: string | null
          parent_record_id?: string | null
          payload?: Json
          provider?: string | null
          record_type: string
          run_id: string
          schema_version?: number
          source: string
          strategy_status?: string | null
          strategy_type?: string | null
          target?: string | null
          theme?: string | null
          trading_date: string
        }
        Update: {
          created_at?: string
          decision_id?: string | null
          decision_index?: number | null
          duplicate_of_record_id?: string | null
          execution_mode?: string | null
          journal_record_id?: string
          order_id?: string | null
          parent_record_id?: string | null
          payload?: Json
          provider?: string | null
          record_type?: string
          run_id?: string
          schema_version?: number
          source?: string
          strategy_status?: string | null
          strategy_type?: string | null
          target?: string | null
          theme?: string | null
          trading_date?: string
        }
        Relationships: []
      }
      learning_reports: {
        Row: {
          created_at: string
          learning_report_id: string
          payload: Json
          report_date: string
          report_type: string
          run_id: string | null
          schema_version: number
          target: string | null
          theme: string | null
        }
        Insert: {
          created_at?: string
          learning_report_id: string
          payload?: Json
          report_date: string
          report_type: string
          run_id?: string | null
          schema_version?: number
          target?: string | null
          theme?: string | null
        }
        Update: {
          created_at?: string
          learning_report_id?: string
          payload?: Json
          report_date?: string
          report_type?: string
          run_id?: string | null
          schema_version?: number
          target?: string | null
          theme?: string | null
        }
        Relationships: []
      }
      lifecycle_records: {
        Row: {
          created_at: string
          decision_id: string | null
          journal_record_id: string | null
          lifecycle_record_id: string
          order_id: string | null
          outcome_type: string | null
          payload: Json
          record_type: string
          run_id: string
          schema_version: number
          target: string | null
          theme: string | null
          trading_date: string
        }
        Insert: {
          created_at?: string
          decision_id?: string | null
          journal_record_id?: string | null
          lifecycle_record_id: string
          order_id?: string | null
          outcome_type?: string | null
          payload?: Json
          record_type: string
          run_id: string
          schema_version?: number
          target?: string | null
          theme?: string | null
          trading_date: string
        }
        Update: {
          created_at?: string
          decision_id?: string | null
          journal_record_id?: string | null
          lifecycle_record_id?: string
          order_id?: string | null
          outcome_type?: string | null
          payload?: Json
          record_type?: string
          run_id?: string
          schema_version?: number
          target?: string | null
          theme?: string | null
          trading_date?: string
        }
        Relationships: []
      }
      provider_errors: {
        Row: {
          created_at: string
          error_type: string
          message: string
          payload: Json
          provider: string
          provider_error_id: string
          run_id: string | null
          schema_version: number
          source: string | null
          target: string | null
        }
        Insert: {
          created_at?: string
          error_type: string
          message: string
          payload?: Json
          provider: string
          provider_error_id: string
          run_id?: string | null
          schema_version?: number
          source?: string | null
          target?: string | null
        }
        Update: {
          created_at?: string
          error_type?: string
          message?: string
          payload?: Json
          provider?: string
          provider_error_id?: string
          run_id?: string | null
          schema_version?: number
          source?: string | null
          target?: string | null
        }
        Relationships: []
      }
      provider_snapshots: {
        Row: {
          as_of: string | null
          created_at: string
          payload: Json
          provider: string
          provider_snapshot_id: string
          retrieved_at: string | null
          schema_version: number
          source_endpoint: string | null
          source_id: string | null
          source_url: string | null
          target: string | null
          theme: string | null
        }
        Insert: {
          as_of?: string | null
          created_at?: string
          payload?: Json
          provider: string
          provider_snapshot_id: string
          retrieved_at?: string | null
          schema_version?: number
          source_endpoint?: string | null
          source_id?: string | null
          source_url?: string | null
          target?: string | null
          theme?: string | null
        }
        Update: {
          as_of?: string | null
          created_at?: string
          payload?: Json
          provider?: string
          provider_snapshot_id?: string
          retrieved_at?: string | null
          schema_version?: number
          source_endpoint?: string | null
          source_id?: string | null
          source_url?: string | null
          target?: string | null
          theme?: string | null
        }
        Relationships: []
      }
      runs: {
        Row: {
          created_at: string
          current_date: string | null
          payload: Json
          run_id: string
          scheduled_date: string | null
          schema_version: number
          status: string | null
          trigger_type: string | null
          window_end: string | null
          window_start: string | null
        }
        Insert: {
          created_at?: string
          current_date?: string | null
          payload?: Json
          run_id: string
          scheduled_date?: string | null
          schema_version?: number
          status?: string | null
          trigger_type?: string | null
          window_end?: string | null
          window_start?: string | null
        }
        Update: {
          created_at?: string
          current_date?: string | null
          payload?: Json
          run_id?: string
          scheduled_date?: string | null
          schema_version?: number
          status?: string | null
          trigger_type?: string | null
          window_end?: string | null
          window_start?: string | null
        }
        Relationships: []
      }
      storage_write_audit: {
        Row: {
          attempted_record_count: number
          created_at: string
          error_count: number
          payload: Json
          provider: string
          run_id: string | null
          schema_version: number
          storage_write_audit_id: string
          table_name: string
          written_record_count: number
        }
        Insert: {
          attempted_record_count?: number
          created_at?: string
          error_count?: number
          payload?: Json
          provider: string
          run_id?: string | null
          schema_version?: number
          storage_write_audit_id: string
          table_name: string
          written_record_count?: number
        }
        Update: {
          attempted_record_count?: number
          created_at?: string
          error_count?: number
          payload?: Json
          provider?: string
          run_id?: string | null
          schema_version?: number
          storage_write_audit_id?: string
          table_name?: string
          written_record_count?: number
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  prescient_storage: {
    Enums: {},
  },
} as const
