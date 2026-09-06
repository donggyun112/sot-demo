export interface paths {
    "/api/v1/auth/google": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Google */
        post: operations["google_api_v1_auth_google_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout All */
        post: operations["logout_all_api_v1_auth_logout_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh */
        post: operations["refresh_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tosses/{token}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Public Toss */
        get: operations["public_toss_api_v1_tosses__token__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List For Actor */
        get: operations["list_for_actor_api_v1_workspaces_get"];
        put?: never;
        /** Create Workspace */
        post: operations["create_workspace_api_v1_workspaces_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_api_v1_workspaces__workspace_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/agent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Run Agent */
        post: operations["run_agent_api_v1_workspaces__workspace_id__branches__branch_id__agent_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundle-preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Preview */
        get: operations["preview_api_v1_workspaces__workspace_id__branches__branch_id__bundle_preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Publish */
        post: operations["publish_api_v1_workspaces__workspace_id__branches__branch_id__bundles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/curation-ops": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Curate */
        post: operations["curate_api_v1_workspaces__workspace_id__branches__branch_id__curation_ops_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/turns": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Turns For Branch */
        get: operations["list_branch_turns"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/bundles/{bundle_id}/tosses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Toss */
        post: operations["create_toss_api_v1_workspaces__workspace_id__bundles__bundle_id__tosses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List For Workspace */
        get: operations["list_workspace_documents"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_api_v1_workspaces__workspace_id__documents__document_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Proposals For Document */
        get: operations["list_document_proposals"];
        put?: never;
        /** Create Proposal */
        post: operations["create_proposal_api_v1_workspaces__workspace_id__documents__document_id__proposals_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/revisions/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Revision */
        get: operations["revision_api_v1_workspaces__workspace_id__documents__document_id__revisions__number__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Sessions For Document */
        get: operations["list_document_sessions"];
        put?: never;
        /** Create */
        post: operations["create_api_v1_workspaces__workspace_id__documents__document_id__sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add */
        post: operations["add_api_v1_workspaces__workspace_id__members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/members/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current Member */
        get: operations["get_current_workspace_member"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Proposal */
        get: operations["read_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__get"];
        /** Revise Proposal */
        put: operations["revise_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/decisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide Proposal */
        post: operations["decide_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__decisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/merge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Merge Proposal */
        post: operations["merge_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__merge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_api_v1_workspaces__workspace_id__sessions__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/branches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Branches For Session */
        get: operations["list_session_branches"];
        put?: never;
        /** Branch */
        post: operations["branch_api_v1_workspaces__workspace_id__sessions__session_id__branches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/tosses/{token}/fork": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Fork Toss */
        post: operations["fork_toss_api_v1_workspaces__workspace_id__tosses__token__fork_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/tosses/{toss_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Revoke Toss */
        delete: operations["revoke_toss_api_v1_workspaces__workspace_id__tosses__toss_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AddWorkspaceMemberRequest */
        AddWorkspaceMemberRequest: {
            role: components["schemas"]["WorkspaceRole"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * ApprovalDecision
         * @enum {string}
         */
        ApprovalDecision: "approve" | "reject";
        /** ApprovalResponse */
        ApprovalResponse: {
            /**
             * Approver User Id
             * Format: uuid
             */
            approver_user_id: string;
            /**
             * Decided At
             * Format: date-time
             */
            decided_at: string;
            decision: components["schemas"]["ApprovalDecision"];
            /**
             * Proposal Id
             * Format: uuid
             */
            proposal_id: string;
            /** Version */
            version: number;
        };
        /** AttributionResponse */
        AttributionResponse: {
            /** Author Display Name */
            author_display_name: string;
            /**
             * Published At
             * Format: date-time
             */
            published_at: string;
            /** Title */
            title: string;
        };
        /** AuthResponse */
        AuthResponse: {
            /** Access Token */
            access_token: string;
            /**
             * Token Type
             * @default bearer
             * @constant
             */
            token_type: "bearer";
            user: components["schemas"]["UserResponse"];
        };
        /** BranchMutationResponse */
        BranchMutationResponse: {
            /** Branch Version */
            branch_version: number;
            /**
             * Resource Id
             * Format: uuid
             */
            resource_id: string;
        };
        /** BranchResponse */
        BranchResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** BundleItemResponse */
        BundleItemResponse: {
            /** Content */
            content: string;
            /**
             * Provenance
             * @enum {string}
             */
            provenance: "copied" | "edited";
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
            /** Source Ids */
            source_ids: string[];
        };
        /** CitationRequest */
        CitationRequest: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Bundle Item Position */
            bundle_item_position: number;
            /** Claim Anchor */
            claim_anchor: string;
        };
        /** CitationResponse */
        CitationResponse: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Bundle Item Position */
            bundle_item_position: number;
            /** Claim Anchor */
            claim_anchor: string;
        };
        /** CreateProposalRequest */
        CreateProposalRequest: {
            /** Additional Approver Ids */
            additional_approver_ids?: string[];
            /** Bundle Ids */
            bundle_ids?: string[];
            /** Citations */
            citations: components["schemas"]["CitationRequest"][];
            /** Content */
            content: string;
            /**
             * Source Session Id
             * Format: uuid
             */
            source_session_id: string;
        };
        /** CreateTossRequest */
        CreateTossRequest: {
            /** Expires At */
            expires_at?: string | null;
        };
        /** CreateWorkspaceRequest */
        CreateWorkspaceRequest: {
            /** Name */
            name: string;
        };
        /** CreatedSessionResponse */
        CreatedSessionResponse: {
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
        };
        /** CreatedTossResponse */
        CreatedTossResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Token */
            token: string;
        };
        /** CurationRequest */
        CurationRequest: {
            /** Expected Version */
            expected_version: number;
            /** Operation */
            operation: components["schemas"]["DropTurnRequest"] | components["schemas"]["EditTurnRequest"] | components["schemas"]["JoinTurnsRequest"];
        };
        /** CurrentWorkspaceMemberResponse */
        CurrentWorkspaceMemberResponse: {
            /** Permissions */
            permissions: components["schemas"]["Permission"][];
            role: components["schemas"]["WorkspaceRole"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** DecideProposalRequest */
        DecideProposalRequest: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "reject";
            /** Expected Version */
            expected_version: number;
        };
        /** DocumentResponse */
        DocumentResponse: {
            current_revision: components["schemas"]["RevisionResponse"];
            document: components["schemas"]["DocumentSummaryResponse"];
        };
        /** DocumentSummaryResponse */
        DocumentSummaryResponse: {
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** DropTurnRequest */
        DropTurnRequest: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "drop";
            /**
             * Turn Id
             * Format: uuid
             */
            turn_id: string;
        };
        /** EditTurnRequest */
        EditTurnRequest: {
            /** Content */
            content: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "edit";
            /**
             * Turn Id
             * Format: uuid
             */
            turn_id: string;
        };
        /** EmptySessionRequest */
        EmptySessionRequest: Record<string, never>;
        /** ForkRequest */
        ForkRequest: Record<string, never>;
        /** ForkResponse */
        ForkResponse: {
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** JoinTurnsRequest */
        JoinTurnsRequest: {
            /** Content */
            content: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "join";
            /** Turn Ids */
            turn_ids: string[];
        };
        /** LoginRequest */
        LoginRequest: {
            /** Credential */
            credential: string;
        };
        /** MergeProposalRequest */
        MergeProposalRequest: {
            /** Expected Version */
            expected_version: number;
        };
        /** MergeProposalResponse */
        MergeProposalResponse: {
            /**
             * Proposal Id
             * Format: uuid
             */
            proposal_id: string;
            publication: components["schemas"]["PublicationResponse"] | null;
            status: components["schemas"]["ProposalStatus"];
            /** Version */
            version: number;
        };
        /**
         * Permission
         * @enum {string}
         */
        Permission: "workspace.manage" | "document.create" | "document.read" | "document.publish" | "session.create" | "session.read" | "session.participate";
        /** ProposalResponse */
        ProposalResponse: {
            /** Approvals */
            approvals: components["schemas"]["ApprovalResponse"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            current_version: components["schemas"]["ProposalVersionResponse"];
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Source Session Id
             * Format: uuid
             */
            source_session_id: string;
            status: components["schemas"]["ProposalStatus"];
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /**
         * ProposalStatus
         * @enum {string}
         */
        ProposalStatus: "open" | "approved" | "rejected" | "stale" | "merged";
        /** ProposalVersionResponse */
        ProposalVersionResponse: {
            /** Additional Approver Ids */
            additional_approver_ids: string[];
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Bundle Ids */
            bundle_ids: string[];
            /** Citations */
            citations: components["schemas"]["CitationResponse"][];
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Proposal Id
             * Format: uuid
             */
            proposal_id: string;
            /** Required Approver Ids */
            required_approver_ids: string[];
            /** Version */
            version: number;
        };
        /** PublicBundleItemResponse */
        PublicBundleItemResponse: {
            /** Content */
            content: string;
            /**
             * Provenance
             * @enum {string}
             */
            provenance: "copied" | "edited";
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
            /** Source Ids */
            source_ids: string[];
        };
        /** PublicBundleResponse */
        PublicBundleResponse: {
            attribution: components["schemas"]["AttributionResponse"];
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Items */
            items: components["schemas"]["PublicBundleItemResponse"][];
            /** Title */
            title: string;
        };
        /** PublicationResponse */
        PublicationResponse: {
            document: components["schemas"]["PublishedDocumentResponse"];
            revision: components["schemas"]["PublishedRevisionResponse"];
        };
        /** PublishBundleRequest */
        PublishBundleRequest: {
            /** Expected Version */
            expected_version: number;
            /** Title */
            title: string;
        };
        /** PublishedDocumentResponse */
        PublishedDocumentResponse: {
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** PublishedRevisionResponse */
        PublishedRevisionResponse: {
            /** Citations */
            citations: components["schemas"]["CitationResponse"][];
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Number */
            number: number;
            /** Proposal Id */
            proposal_id: string | null;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** ReviseProposalRequest */
        ReviseProposalRequest: {
            /** Additional Approver Ids */
            additional_approver_ids?: string[] | null;
            /** Bundle Ids */
            bundle_ids: string[];
            /** Citations */
            citations: components["schemas"]["CitationRequest"][];
            /** Content */
            content: string;
            /** Expected Version */
            expected_version: number;
        };
        /** RevisionCitationResponse */
        RevisionCitationResponse: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Bundle Item Position */
            bundle_item_position: number;
            /** Claim Anchor */
            claim_anchor: string;
        };
        /** RevisionResponse */
        RevisionResponse: {
            /** Citations */
            citations: components["schemas"]["RevisionCitationResponse"][];
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Number */
            number: number;
            /** Proposal Id */
            proposal_id: string | null;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** SessionResponse */
        SessionResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Document Id */
            document_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            status: components["schemas"]["SessionStatus"];
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /**
         * SessionStatus
         * @enum {string}
         */
        SessionStatus: "open" | "closed";
        /** TurnResponse */
        TurnResponse: {
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Ordinal */
            ordinal: number;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** UserResponse */
        UserResponse: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** WorkspaceMemberResponse */
        WorkspaceMemberResponse: {
            role: components["schemas"]["WorkspaceRole"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** WorkspaceResponse */
        WorkspaceResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /**
         * WorkspaceRole
         * @enum {string}
         */
        WorkspaceRole: "owner" | "member" | "viewer";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    google_api_v1_auth_google_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    logout_all_api_v1_auth_logout_all_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    refresh_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthResponse"];
                };
            };
        };
    };
    me_api_v1_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
        };
    };
    public_toss_api_v1_tosses__token__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicBundleResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_for_actor_api_v1_workspaces_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResponse"][];
                };
            };
        };
    };
    create_workspace_api_v1_workspaces_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateWorkspaceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_api_v1_workspaces__workspace_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    run_agent_api_v1_workspaces__workspace_id__branches__branch_id__agent_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preview_api_v1_workspaces__workspace_id__branches__branch_id__bundle_preview_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BundleItemResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    publish_api_v1_workspaces__workspace_id__branches__branch_id__bundles_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PublishBundleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchMutationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    curate_api_v1_workspaces__workspace_id__branches__branch_id__curation_ops_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CurationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchMutationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_branch_turns: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TurnResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_toss_api_v1_workspaces__workspace_id__bundles__bundle_id__tosses_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                bundle_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateTossRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedTossResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_workspace_documents: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentSummaryResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_api_v1_workspaces__workspace_id__documents__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_document_proposals: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_proposal_api_v1_workspaces__workspace_id__documents__document_id__proposals_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revision_api_v1_workspaces__workspace_id__documents__document_id__revisions__number__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
                number: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RevisionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_document_sessions: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_api_v1_workspaces__workspace_id__documents__document_id__sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EmptySessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedSessionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_api_v1_workspaces__workspace_id__members_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddWorkspaceMemberRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMemberResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_current_workspace_member: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurrentWorkspaceMemberResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revise_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviseProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decide_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__decisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecideProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    merge_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__merge_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MergeProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MergeProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_api_v1_workspaces__workspace_id__sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_session_branches: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    branch_api_v1_workspaces__workspace_id__sessions__session_id__branches_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EmptySessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    fork_toss_api_v1_workspaces__workspace_id__tosses__token__fork_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                token: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ForkRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ForkResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revoke_toss_api_v1_workspaces__workspace_id__tosses__toss_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                toss_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_healthz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
}
